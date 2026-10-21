"""Upload validation and lossless compression (spinalcure/uploads.py, spinalcure/compress.py)."""
import gzip
import io
import random
import zipfile

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django.http import HttpResponse
from PIL import Image, ImageChops

from spinalcure import uploads
from spinalcure.compress import DownloadGzipMiddleware, recompress_zip


def make_png(size=(300, 200), colours=None, mode='RGB'):
    rng = random.Random(1)
    img = Image.new(mode, size)
    pal = colours or [tuple(rng.randrange(256) for _ in range(len(mode))) for _ in range(12)]
    px = img.load()
    for x in range(size[0]):
        for y in range(size[1]):
            px[x, y] = pal[(x // 25 + y // 25) % len(pal)]
    buf = io.BytesIO()
    img.save(buf, 'PNG', compress_level=1)           # a deliberately weak encoding, as many tools produce
    return buf.getvalue()


def up(data, name):
    return SimpleUploadedFile(name, data)


def pixels_equal(a, b):
    with Image.open(io.BytesIO(a)) as x, Image.open(io.BytesIO(b)) as y:
        return x.size == y.size and ImageChops.difference(x.convert('RGBA'), y.convert('RGBA')).getbbox() is None


# ── images ──────────────────────────────────────────────────────────────────────────────────────────

def test_png_gets_smaller_with_identical_pixels_and_a_random_name():
    original = make_png()
    out = uploads.checked_image(up(original, 'Patient Photo.PNG'))
    data = out.read()
    assert len(data) < len(original) and pixels_equal(original, data)
    assert out.name.endswith('.png') and 'Patient' not in out.name and out.size == len(data)


def test_png_with_transparency_stays_transparent():
    original = make_png(mode='RGBA', colours=[(255, 0, 0, 255), (0, 0, 255, 128), (0, 0, 0, 0)])
    data = uploads.checked_image(up(original, 'a.png')).read()
    assert pixels_equal(original, data)
    with Image.open(io.BytesIO(data)) as im:
        assert im.convert('RGBA').getpixel((60, 60))[3] in (0, 128, 255)


def test_png_trailing_junk_is_dropped():
    original = make_png() + b'<script>alert(1)</script>'
    data = uploads.checked_image(up(original, 'a.png')).read()
    assert b'<script>' not in data and pixels_equal(make_png(), data)


def test_jpeg_loses_gps_but_keeps_pixels_and_orientation():
    rng = random.Random(2)
    img = Image.effect_noise((320, 240), 40).convert('RGB')
    exif = Image.Exif()
    exif[0x0112] = 6
    exif[0x010F] = 'PhoneMaker'
    exif[0x8825] = {1: 'N', 2: (13.0, 4.0, 3.0), 3: 'E', 4: (80.0, 12.0, 0.0)}
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=90, exif=exif)
    original = buf.getvalue()
    assert b'PhoneMaker' in original
    data = uploads.checked_image(up(original, 'IMG_001.jpg')).read()
    assert b'PhoneMaker' not in data and len(data) < len(original)
    with Image.open(io.BytesIO(data)) as out:
        e = out.getexif()
        assert e.get(0x0112) == 6 and 0x8825 not in e and 0x010F not in e
    with Image.open(io.BytesIO(original)) as a, Image.open(io.BytesIO(data)) as b:
        assert ImageChops.difference(a, b).getbbox() is None             # the picture itself is untouched


def test_lossy_webp_is_left_alone_and_lossless_webp_is_kept_exact():
    img = Image.effect_noise((200, 200), 30).convert('RGB')
    lossy, lossless = io.BytesIO(), io.BytesIO()
    img.save(lossy, 'WEBP', quality=80)
    img.save(lossless, 'WEBP', lossless=True, method=0)
    out = uploads.checked_image(up(lossy.getvalue(), 'a.webp')).read()
    assert out == lossy.getvalue()
    out2 = uploads.checked_image(up(lossless.getvalue(), 'b.webp')).read()
    assert pixels_equal(lossless.getvalue(), out2) and len(out2) <= len(lossless.getvalue())


@pytest.mark.parametrize('name, data', [
    ('page.png', b'<html><script>alert(1)</script></html>'),
    ('evil.jpg', b'GIF89a not really'),
    ('empty.png', b''),
    ('doc.png', b'%PDF-1.7 ...')])
def test_fake_images_are_rejected(name, data):
    with pytest.raises(uploads.UploadRejected):
        uploads.checked_image(up(data, name))


def test_oversized_image_is_rejected(monkeypatch):
    monkeypatch.setattr(uploads, 'MAX_IMAGE_BYTES', 100)
    with pytest.raises(uploads.UploadRejected):
        uploads.checked_image(up(make_png(), 'a.png'))


def test_checking_twice_does_not_reprocess():
    f = up(make_png(), 'a.png')
    uploads.checked_image(f)
    name, size = f.name, f.size
    uploads.checked_image(f)
    assert (f.name, f.size) == (name, size)


# ── videos ──────────────────────────────────────────────────────────────────────────────────────────

MP4 = b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom' + b'\x00' * 64
WEBM = b'\x1a\x45\xdf\xa3' + b'\x00' * 64


def test_real_video_headers_are_accepted_and_renamed(monkeypatch):
    monkeypatch.setattr(uploads.shutil, 'which', lambda _n: None)          # no ffmpeg: bytes untouched
    for name, data, ext in [('clip.MP4', MP4, '.mp4'), ('t.mov', MP4, '.mov'), ('v.webm', WEBM, '.webm')]:
        out = uploads.checked_video(up(data, name))
        assert out.name.endswith(ext) and 'clip' not in out.name and out.read() == data


@pytest.mark.parametrize('name, data', [
    ('x.mp4', b'<html>not a video</html>'),
    ('x.mp4', WEBM),                                      # WebM bytes under an MP4 name
    ('x.webm', MP4),
    ('x.avi', MP4),
    ('x.mp4', b'\x00\x00\x00\x18ftypheic' + b'\x00' * 20),   # a HEIC photo
    ('x.exe', b'MZ' + b'\x00' * 40)])
def test_fake_videos_are_rejected(name, data):
    with pytest.raises(uploads.UploadRejected):
        uploads.checked_video(up(data, name))


def test_oversized_video_is_rejected(monkeypatch):
    monkeypatch.setattr(uploads, 'MAX_VIDEO_BYTES', 10)
    with pytest.raises(uploads.UploadRejected):
        uploads.checked_video(up(MP4, 'x.mp4'))


def test_ffmpeg_failure_keeps_the_original_bytes(monkeypatch):
    monkeypatch.setattr(uploads.shutil, 'which', lambda _n: '/usr/bin/ffmpeg')
    def boom(*a, **k):
        raise OSError('ffmpeg exploded')
    monkeypatch.setattr(uploads.subprocess, 'run', boom)
    assert uploads.checked_video(up(MP4, 'x.mp4')).read() == MP4


# ── every entry point: model fields ─────────────────────────────────────────────────────────────────

def test_field_validator_rejects_fakes_and_accepts_real_images():
    with pytest.raises(ValidationError):
        uploads.validate_safe_image(up(b'not an image', 'a.png'))
    uploads.validate_safe_image(up(make_png(), 'a.png'))
    with pytest.raises(ValidationError):
        uploads.validate_safe_video(up(b'nope', 'a.mp4'))


@pytest.mark.django_db
def test_saving_a_model_without_a_form_still_validates_and_compresses():
    from clinic.models import GalleryItem
    original = make_png()
    item = GalleryItem(kind='photo', title='t', image=up(original, 'big.png'))
    item.save()
    assert item.image.size < len(original) and item.image.name.endswith('.png') and 'big' not in item.image.name
    with pytest.raises(uploads.UploadRejected):
        GalleryItem(kind='photo', title='bad', image=up(b'<svg onload=alert(1)>', 'x.png')).save()


@pytest.mark.django_db
def test_forms_reject_a_fake_image_everywhere_it_is_uploaded(clinic_profile):
    from courses.forms import CourseForm
    from courses.models import Course
    data = {'title': 'T', 'short_description': 's', 'description': 'd', 'platform': 'offline', 'fees': '0',
            'duration': '1 day', 'is_published': 'on', 'outcomes': 'o', 'course_content': 'c'}
    bad = CourseForm(data, {'image': up(b'<html>', 'x.png')})
    assert not bad.is_valid() and 'image' in bad.errors
    good = CourseForm(data, {'image': up(make_png(), 'x.png')})
    assert good.is_valid(), good.errors


# ── downloads ───────────────────────────────────────────────────────────────────────────────────────

def _download(accept, body=b'a,b,c\n' * 400, ctype='text/csv', disposition='attachment; filename="x.csv"'):
    def view(request):
        r = HttpResponse(body, content_type=ctype)
        if disposition:
            r['Content-Disposition'] = disposition
        return r
    return DownloadGzipMiddleware(view)(RequestFactory().get('/', HTTP_ACCEPT_ENCODING=accept))


def test_csv_downloads_are_gzipped_only_when_accepted():
    r = _download('gzip, deflate')
    assert r['Content-Encoding'] == 'gzip' and gzip.decompress(r.content) == b'a,b,c\n' * 400
    assert 'Content-Encoding' not in _download('identity')
    assert 'Content-Encoding' not in _download('gzip', disposition='')            # a page, not a download
    assert 'Content-Encoding' not in _download('gzip', ctype='application/pdf')


def test_excel_zip_is_rewritten_with_identical_members():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        z.writestr('xl/sheet1.xml', '<row>' + 'hello world ' * 3000 + '</row>')
        z.writestr('[Content_Types].xml', '<Types/>')
    out = recompress_zip(buf.getvalue())
    assert len(out) <= len(buf.getvalue())
    with zipfile.ZipFile(io.BytesIO(out)) as a, zipfile.ZipFile(io.BytesIO(buf.getvalue())) as b:
        assert a.namelist() == b.namelist() and all(a.read(n) == b.read(n) for n in a.namelist())
    assert recompress_zip(b'not a zip') == b'not a zip'
