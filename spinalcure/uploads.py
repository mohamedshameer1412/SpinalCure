"""Everything about uploaded files in one place.

* RandomName: upload paths with random names, so a file cannot be found by guessing its original filename.
* checked_image / checked_video: validate the real content (not the file name or the browser's MIME type), reject
  anything else, and shrink the file LOSSLESSLY: the decoded pixels / the video streams are identical afterwards.
* SafeImageField / SafeVideoField: model fields that run those checks for every entry point (forms, the Django
  admin, the API, scripts), so no upload path can forget to validate.

What "lossless" means here, per format (every result is decoded and compared with the original, and the original
is kept whenever it is not identical or not smaller):
  PNG   zlib level 9 + optimised filters, and an exact palette when the image has at most 256 colours;
  WebP  re-encoded losslessly, only if the file already is lossless (a lossy WebP is left untouched);
  JPEG  pixels untouched: EXIF/GPS, XMP, thumbnails and comments are removed (orientation and colour profile kept);
  video untouched unless ffmpeg is installed, then a stream copy (no re-encode) that drops location metadata and
        moves the index to the front for fast start. Video is already compressed: re-encoding it "losslessly"
        would make it several times bigger.
"""
import io
import os
import shutil
import struct
import subprocess
import tempfile
import uuid
from pathlib import Path

from django.utils.deconstruct import deconstructible


@deconstructible
class RandomName:
    def __init__(self, folder):
        self.folder = folder

    def __call__(self, instance, filename):
        ext = os.path.splitext(filename)[1].lower()[:10]
        return f'{self.folder}/{uuid.uuid4().hex}{ext}'

    def __eq__(self, other):
        return isinstance(other, RandomName) and other.folder == self.folder


MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
IMAGE_EXT = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp', 'GIF': '.gif'}
VIDEO_EXTENSIONS = ('.mp4', '.webm', '.mov')
MAX_VIDEO_BYTES = 80 * 1024 * 1024
_NOT_VIDEO_BRANDS = {b'heic', b'heix', b'hevc', b'mif1', b'msf1', b'avif', b'avis', b'M4A ', b'M4B ', b'3gp4'}
_DONE = '_spinal_checked'


class UploadRejected(ValueError):
    pass


# -- helpers ----------------------------------------------------------------------------------------------

def _replace_content(upload, data):
    """Swap the bytes of an uploaded file in place, so callers that hold the object see the smaller file."""
    f = upload.file
    f.seek(0)
    f.truncate(0)
    f.write(data)
    f.seek(0)
    upload.size = len(data)


def _same_pixels(a_bytes, b_bytes):
    """True when both images decode to exactly the same pixels (colours and transparency)."""
    from PIL import Image, ImageChops
    with Image.open(io.BytesIO(a_bytes)) as a, Image.open(io.BytesIO(b_bytes)) as b:
        a.load()
        b.load()
        if a.size != b.size:
            return False
        try:
            return ImageChops.difference(a.convert('RGBA'), b.convert('RGBA')).getbbox() is None
        except Exception:                      # e.g. 16-bit modes: compare the raw samples
            return a.mode == b.mode and a.tobytes() == b.tobytes()


def _png_candidates(data):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as img:
        if getattr(img, 'n_frames', 1) > 1:     # animated PNG: leave alone
            return
        img.load()
        kw = {'optimize': True, 'compress_level': 9}
        for key in ('icc_profile', 'transparency', 'dpi'):
            if key in img.info:
                kw[key] = img.info[key]
        variants = [img]
        if img.mode in ('RGB', 'RGBA') and img.getcolors(256):       # few colours: an exact palette is far smaller
            method = Image.Quantize.FASTOCTREE if img.mode == 'RGBA' else Image.Quantize.MEDIANCUT
            variants.append(img.quantize(colors=256, method=method, dither=Image.Dither.NONE))
        for v in variants:
            buf = io.BytesIO()
            v.save(buf, 'PNG', **({k: x for k, x in kw.items() if not (v is not img and k == 'transparency')}))
            yield buf.getvalue()


def _webp_candidates(data):
    from PIL import Image
    head = data[12:120]
    if b'VP8L' not in head or b'VP8 ' in head:        # lossy WebP: re-encoding would change the pixels
        return
    with Image.open(io.BytesIO(data)) as img:
        if getattr(img, 'n_frames', 1) > 1:
            return
        img.load()
        buf = io.BytesIO()
        img.save(buf, 'WEBP', lossless=True, quality=100, method=6, exact=True)
        yield buf.getvalue()


def _exif_orientation_segment(value):
    # a complete, minimal EXIF block holding only the Orientation tag
    tiff = b'MM\x00*\x00\x00\x00\x08' + b'\x00\x01' + b'\x01\x12\x00\x03\x00\x00\x00\x01' + struct.pack('>H', value) + b'\x00\x00' + b'\x00\x00\x00\x00'
    body = b'Exif\x00\x00' + tiff
    return b'\xff\xe1' + struct.pack('>H', len(body) + 2) + body


def _jpeg_candidates(data):
    """The same JPEG stream without EXIF/GPS/XMP/comments. The compressed picture data is copied byte for byte."""
    from PIL import Image
    if data[:2] != b'\xff\xd8':
        return
    with Image.open(io.BytesIO(data)) as img:
        orientation = img.getexif().get(0x0112, 1)
    segments, i, tail = [], 2, b''
    while i < len(data):
        if data[i] != 0xFF:
            return
        while data[i + 1] == 0xFF:
            i += 1
        marker = data[i + 1]
        if marker == 0xDA:                                 # start of scan: everything after is picture data
            tail = data[i:]
            break
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:
            segments.append((marker, data[i:i + 2]))
            i += 2
            continue
        length = struct.unpack('>H', data[i + 2:i + 4])[0]
        seg = data[i:i + 2 + length]
        icc = marker == 0xE2 and seg[4:16] == b'ICC_PROFILE\x00'
        if marker not in range(0xE0, 0xF0) and marker != 0xFE or marker in (0xE0, 0xEE) or icc:
            segments.append((marker, seg))                 # tables, frame header, JFIF, Adobe, colour profile
        i += 2 + length
    if not tail:
        return
    if orientation in range(2, 9):                         # keep the rotation the camera recorded
        at = 1 if segments and segments[0][0] == 0xE0 else 0
        segments.insert(at, (0xE1, _exif_orientation_segment(orientation)))
    yield b'\xff\xd8' + b''.join(seg for _m, seg in segments) + tail


def optimize_image(data, fmt):
    """Smallest lossless version of the image bytes, or the original when nothing verified is smaller."""
    make = {'PNG': _png_candidates, 'WEBP': _webp_candidates, 'JPEG': _jpeg_candidates}.get(fmt)
    best = data
    if make:
        try:
            for cand in make(data):
                if len(cand) < len(best) and _same_pixels(data, cand):
                    best = cand
        except Exception:
            return data
    return best


def _must_be_clean_upload(upload):
    from django.utils.translation import gettext
    if upload is None:
        return False
    if getattr(upload, _DONE, False):
        return False
    if not hasattr(upload, 'file'):
        raise UploadRejected(gettext('This file is not a valid upload.'))
    return True


# -- images -----------------------------------------------------------------------------------------------

def checked_image(upload):
    """Return the upload if Pillow can read it as a JPEG/PNG/WebP/GIF within the size limits, renamed to a random
    name with the extension of its real format, and losslessly optimised (see the module docstring). A file that
    only claims to be an image (or a valid image with something else appended, saved as .html/.svg) is never stored
    under a name the web server would execute or render as a page. Raises UploadRejected with a user-facing
    message. Safe to call twice on the same upload."""
    from django.utils.translation import gettext
    from PIL import Image
    if not _must_be_clean_upload(upload):
        return upload
    if upload.size > MAX_IMAGE_BYTES:
        raise UploadRejected(gettext('Image is larger than 8 MB.'))
    try:
        upload.seek(0)
        with Image.open(upload) as img:
            fmt = img.format
            img.verify()
        upload.seek(0)
        with Image.open(upload) as img:
            if img.width * img.height > MAX_IMAGE_PIXELS:
                raise UploadRejected(gettext('Image dimensions are too large.'))
    except UploadRejected:
        raise
    except Exception:
        raise UploadRejected(gettext('This file is not a valid image.'))
    if fmt not in IMAGE_EXT:
        raise UploadRejected(gettext('Use a JPEG, PNG or WebP image.'))
    upload.seek(0)
    data = upload.read()
    smaller = optimize_image(data, fmt)
    if len(smaller) < len(data):
        _replace_content(upload, smaller)
    upload.seek(0)
    upload.name = f'{uuid.uuid4().hex}{IMAGE_EXT[fmt]}'
    setattr(upload, _DONE, True)
    return upload


# -- videos -----------------------------------------------------------------------------------------------

def _remux(data, ext):
    """Stream copy through ffmpeg when it is installed: nothing is re-encoded, location metadata is dropped and
    (mp4/mov) the index moves to the front so playback starts at once. Any problem keeps the original bytes."""
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        return data
    try:
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp, 'in' + ext), Path(tmp, 'out' + ext)
            src.write_bytes(data)
            cmd = [ffmpeg, '-v', 'error', '-y', '-i', str(src), '-map', '0', '-c', 'copy', '-map_metadata', '-1']
            if ext != '.webm':
                cmd += ['-movflags', '+faststart']
            subprocess.run(cmd + [str(dst)], check=True, timeout=120, capture_output=True)
            out = dst.read_bytes()
        return out if 0 < len(out) <= len(data) * 1.02 else data
    except Exception:
        return data


def checked_video(upload):
    """Validate a video by its real header (MP4/MOV 'ftyp' box or WebM/EBML signature) and size, give it a random
    name, and stream-copy it when ffmpeg is available. Raises UploadRejected."""
    from django.utils.translation import gettext
    if not _must_be_clean_upload(upload):
        return upload
    ext = os.path.splitext(upload.name or '')[1].lower()
    if ext not in VIDEO_EXTENSIONS:
        raise UploadRejected(gettext('Upload an MP4, WebM or MOV video.'))
    if upload.size > MAX_VIDEO_BYTES:
        raise UploadRejected(gettext('Videos can be at most 80 MB. Upload longer videos to YouTube and paste the link.'))
    upload.seek(0)
    head = upload.read(16)
    upload.seek(0)
    if ext == '.webm':
        ok = head[:4] == b'\x1a\x45\xdf\xa3'
    else:
        ok = head[4:8] == b'ftyp' and head[8:12] not in _NOT_VIDEO_BRANDS
    if not ok:
        raise UploadRejected(gettext('This file is not a valid video.'))
    data = upload.read()
    smaller = _remux(data, ext)
    if smaller is not data and len(smaller) < len(data) * 1.02:
        _replace_content(upload, smaller)
    upload.seek(0)
    upload.name = f'{uuid.uuid4().hex}{ext}'
    setattr(upload, _DONE, True)
    return upload


# -- model fields: every entry point validates and compresses ----------------------------------------------

def _pending_upload(value):
    """The not-yet-saved uploaded file inside a form value / FieldFile / UploadedFile, else None."""
    from django.core.files.uploadedfile import UploadedFile
    if isinstance(value, UploadedFile):
        return value
    if value and not getattr(value, '_committed', True):
        return value.file
    return None


def _validator(check):
    def validate(value):
        from django.core.exceptions import ValidationError
        upload = _pending_upload(value)
        if upload is not None:
            try:
                check(upload)
            except UploadRejected as e:
                raise ValidationError(str(e), code='invalid_upload')
    return validate


validate_safe_image = _validator(checked_image)
validate_safe_video = _validator(checked_video)


def _checked_pre_save(field_cls, check):
    def pre_save(self, model_instance, add):
        file = getattr(model_instance, self.attname)
        upload = _pending_upload(file)
        if upload is not None:
            check(upload)                       # raises UploadRejected for code that skipped form validation
            file.name = upload.name
        return field_cls.pre_save(self, model_instance, add)
    return pre_save


def _plain_deconstruct(path):
    def deconstruct(self):
        name, _path, args, kwargs = super(type(self), self).deconstruct()
        return name, path, args, kwargs
    return deconstruct


def _make_fields():
    from django.db import models

    class SafeImageField(models.ImageField):
        """ImageField that validates and losslessly optimises new uploads. Migrations see a plain ImageField."""
        default_validators = models.ImageField.default_validators + [validate_safe_image]
        pre_save = _checked_pre_save(models.ImageField, checked_image)
        deconstruct = _plain_deconstruct('django.db.models.ImageField')

    class SafeVideoField(models.FileField):
        default_validators = [validate_safe_video]
        pre_save = _checked_pre_save(models.FileField, checked_video)
        deconstruct = _plain_deconstruct('django.db.models.FileField')

    return SafeImageField, SafeVideoField


SafeImageField, SafeVideoField = _make_fields()


def reject_bad_uploads(view):
    """View decorator: a rejected image upload becomes a form error message instead of a server error."""
    from functools import wraps

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except UploadRejected as e:
            from django.contrib import messages
            from django.shortcuts import redirect
            messages.error(request, str(e))
            return redirect(request.get_full_path())
    return wrapper
