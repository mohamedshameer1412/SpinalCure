"""Completion certificate, drawn with the ID-card renderer (Pillow + the bundled Noto fonts) so names in Tamil, Hindi,
Telugu, Malayalam or Kannada are shaped correctly. A4 landscape at 150 dpi."""
import io
from pathlib import Path

from django.conf import settings
from django.urls import reverse
from django.utils.formats import date_format

from idcards import render
from idcards.render import draw_text, hex_rgb, qr_image
from PIL import Image, ImageDraw

W, H = 1754, 1240


def verify_url(cert):
    return settings.SITE_URL.rstrip('/') + reverse('certificate_verify', args=[cert.code])


def _signatory():
    from clinic.models import Practitioner
    p = Practitioner.objects.filter(is_active=True).order_by('-is_chief', 'name').first()
    return (f'{p.title} {p.name}'.strip(), p.designation_tag or p.specialization or '') if p else ('', '')


def draw(cert, scale=1):
    from clinic.models import ClinicProfile
    from idcards.models import IDCardBranding
    reg = cert.registration
    batch, course, st = reg.batch, reg.batch.course, reg.student
    clinic, brand = ClinicProfile.objects.first(), IDCardBranding.get()
    s = scale
    primary = hex_rgb(brand.primary_color)
    accent = hex_rgb(brand.accent_color, (22, 163, 74))
    dark, grey = (31, 41, 55), (107, 114, 128)
    img = Image.new('RGB', (W * s, H * s), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for inset, width in ((34, 8), (58, 2)):
        d.rectangle((inset * s, inset * s, (W - inset) * s, (H - inset) * s), outline=primary, width=width * s)
    cx = W * s // 2
    y = 110
    logo = Path(clinic.logo.path) if clinic and clinic.logo and Path(clinic.logo.path).exists() else None
    if logo:
        lg = Image.open(logo).convert('RGBA')
        lg.thumbnail((120 * s, 120 * s))
        img.paste(lg, (cx - lg.width // 2, y * s), lg)
    draw_text(d, cx, 245 * s, clinic.name if clinic else 'SpinalCure', 40 * s, primary, True, 'center', max_w=1300 * s)
    draw_text(d, cx, 330 * s, 'CERTIFICATE OF COMPLETION', 74 * s, dark, True, 'center', max_w=1400 * s)
    d.rectangle((cx - 90 * s, 442 * s, cx + 90 * s, 448 * s), fill=accent)
    draw_text(d, cx, 470 * s, 'This is to certify that', 32 * s, grey, False, 'center')
    draw_text(d, cx, 540 * s, st.name, 84 * s, primary, True, 'center', max_w=1400 * s)
    draw_text(d, cx, 670 * s, 'has successfully completed the course', 32 * s, grey, False, 'center')
    draw_text(d, cx, 730 * s, course.title, 52 * s, dark, True, 'center', max_w=1400 * s)
    when = date_format(batch.start_date, 'DATE_FORMAT')
    if batch.end_date:
        when += ' – ' + date_format(batch.end_date, 'DATE_FORMAT')
    line = f'{batch.name}  ·  {when}'
    if cert.attendance_percent is not None:
        line += f'  ·  Attendance {cert.attendance_percent}%'
    draw_text(d, cx, 820 * s, line, 28 * s, grey, False, 'center', max_w=1500 * s)
    # signature, issue date and the verification QR
    name, role = _signatory()
    d.line((170 * s, 1040 * s, 560 * s, 1040 * s), fill=dark, width=2 * s)
    if name:
        draw_text(d, 365 * s, 1055 * s, name, 28 * s, dark, True, 'center', max_w=420 * s)
        draw_text(d, 365 * s, 1092 * s, role, 22 * s, grey, False, 'center', max_w=420 * s)
    draw_text(d, cx, 1010 * s, 'Issued ' + date_format(cert.issued_at, 'DATE_FORMAT'), 26 * s, dark, False, 'center')
    draw_text(d, cx, 1052 * s, 'Certificate no. ' + cert.code, 26 * s, dark, True, 'center')
    q = 170 * s
    qx = W * s - 170 * s - q
    img.paste(qr_image(verify_url(cert), q), (qx, 900 * s))
    draw_text(d, qx + q // 2, 900 * s + q + 8 * s, 'Scan to verify', 20 * s, grey, False, 'center')
    return img


def pdf_bytes(cert):
    img = draw(cert, 1)
    out = io.BytesIO()
    img.save(out, 'PDF', resolution=150.0)
    return out.getvalue()


def png_bytes(cert, scale=1):
    return render.to_png_bytes(draw(cert, scale))
