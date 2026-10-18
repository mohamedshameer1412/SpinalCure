"""
Server-side rendering of ID card faces with Pillow (RAQM shaping) and the bundled Noto fonts.

Used for: the public share image / Open Graph preview, and the PNG/PDF download fallbacks. The interactive
card in the browser is HTML; this produces the same information with the same branding.

Each text is split into runs by script and drawn with a font that has those glyphs (the Noto script fonts
carry no Latin letters or punctuation). For right-to-left text runs are laid out in visual order.
"""
import io
import unicodedata
from functools import lru_cache
from pathlib import Path

import qrcode
from django.conf import settings
from django.utils import translation
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from PIL import Image, ImageDraw, ImageFont, ImageOps

BASE_W, BASE_H = 900, 560
FONT_DIR = Path(settings.BASE_DIR) / 'static' / 'fonts'
RAQM = ImageFont.Layout.RAQM

SCRIPT_FONT = {'latin': 'NotoSans', 'tamil': 'NotoSansTamil', 'deva': 'NotoSansDevanagari', 'arabic': 'NotoSansArabic'}


def _script(ch):
    cp = ord(ch)
    if 0x0B80 <= cp <= 0x0BFF:
        return 'tamil'
    if 0x0900 <= cp <= 0x097F:
        return 'deva'
    if 0x0600 <= cp <= 0x06FF or 0x0750 <= cp <= 0x077F or 0xFB50 <= cp <= 0xFDFF or 0xFE70 <= cp <= 0xFEFF:
        return 'arabic'
    return 'latin'


@lru_cache(maxsize=128)
def _font(script, bold, px):
    name = SCRIPT_FONT[script] + ('-Bold' if bold else '-Regular') + '.ttf'
    return ImageFont.truetype(str(FONT_DIR / name), px, layout_engine=RAQM)


def _runs(text):
    """[(script, text)] — neutrals (space, digits, punctuation) join the preceding run so words stay whole."""
    runs = []
    for ch in text:
        sc = _script(ch)
        if unicodedata.category(ch)[0] in 'ZPNS' and runs and sc == 'latin':
            sc = runs[-1][0]                      # a space/digit/punctuation continues the current script run
            if sc != 'latin' and not _font_has(sc, ch):
                sc = 'latin'
        if runs and runs[-1][0] == sc:
            runs[-1] = (sc, runs[-1][1] + ch)
        else:
            runs.append((sc, ch))
    return runs


@lru_cache(maxsize=4096)
def _cmap(script):
    from fontTools.ttLib import TTFont
    return TTFont(str(FONT_DIR / (SCRIPT_FONT[script] + '-Regular.ttf'))).getBestCmap()


def _font_has(script, ch):
    return ord(ch) in _cmap(script)


def text_width(text, px, bold=False):
    return sum(_font(sc, bold, px).getlength(run, direction='rtl' if sc == 'arabic' else 'ltr') for sc, run in _runs(text))


def fit(text, px, max_w, bold=False):
    """Trim with an ellipsis until the text fits."""
    if text_width(text, px, bold) <= max_w:
        return text
    while text and text_width(text + '…', px, bold) > max_w:
        text = text[:-1]
    return (text + '…') if text else ''


def draw_text(draw, x, y, text, px, fill, bold=False, align='left', max_w=None, rtl=False):
    """Draw `text` with its top-left at (x, y); align is left/right/center relative to x."""
    if not text:
        return 0
    if max_w:
        text = fit(text, px, max_w, bold)
    runs = _runs(text)
    if rtl or any(sc == 'arabic' for sc, _unused in runs):
        runs = runs[::-1]                         # visual order for an RTL paragraph
    width = text_width(text, px, bold)
    cx = {'left': x, 'right': x - width, 'center': x - width / 2}[align]
    baseline = y + _font('latin', bold, px).getmetrics()[0]        # one baseline for every font in the line
    for sc, run in runs:
        font = _font(sc, bold, px)
        direction = 'rtl' if sc == 'arabic' else 'ltr'
        draw.text((cx, baseline), run, font=font, fill=fill, direction=direction, anchor='ls')
        cx += font.getlength(run, direction=direction)
    return width


def draw_pair(draw, x, y, label, value, px, label_fill, value_fill, rtl=False, max_w=None, bold_value=False):
    """'Label  value' as two independent items so Latin labels never reorder Arabic/Tamil values."""
    if not value:
        return
    gap = int(px * 0.5)
    label = f'{label}:' if label else ''
    lw = text_width(label, px, False) if label else 0
    room = (max_w - lw - gap) if max_w else None
    if rtl:
        if label:
            draw_text(draw, x, y, label, px, label_fill, False, 'right', rtl=True)
        draw_text(draw, x - lw - (gap if label else 0), y, value, px, value_fill, bold_value, 'right', max_w=room, rtl=True)
    else:
        if label:
            draw_text(draw, x, y, label, px, label_fill, False, 'left')
        draw_text(draw, x + lw + (gap if label else 0), y, value, px, value_fill, bold_value, 'left', max_w=room)


def wrap(text, px, max_w, max_lines, bold=False):
    words, lines, cur = (text or '').split(), [], ''
    for w in words:
        trial = (cur + ' ' + w).strip()
        if text_width(trial, px, bold) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fit(lines[-1] + '…', px, max_w, bold)
    return lines


def hex_rgb(value, default=(22, 101, 52)):
    try:
        v = value.lstrip('#')
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return default


def qr_image(data, size):
    """
    QR on a white square of exactly `size` px. Uses the standard 4-module quiet zone and a whole number of
    pixels per module (no resampling blur), so scanners get uniform, crisp modules at every export scale.
    """
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1, border=0)
    qr.add_data(data)
    qr.make(fit=True)
    modules = qr.modules_count
    quiet = 4
    per_module = max(1, size // (modules + 2 * quiet))
    matrix = qr.make_image(fill_color='black', back_color='white').convert('L')
    code = matrix.resize((modules * per_module, modules * per_module), Image.NEAREST)
    canvas = Image.new('RGB', (size, size), 'white')
    offset = (size - code.width) // 2
    canvas.paste(code.convert('RGB'), (offset, offset))
    return canvas


def _rounded_paste(base, img, box, radius):
    w, h = box[2] - box[0], box[3] - box[1]
    img = ImageOps.fit(img.convert('RGB'), (w, h), Image.LANCZOS)
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
    base.paste(img, (box[0], box[1]), mask)


STATUS_COLORS = {'active': (22, 163, 74), 'deactivated': (217, 119, 6), 'revoked': (220, 38, 38),
                 'expired': (220, 38, 38), 'inactive': (107, 114, 128)}


def status_label(status):
    return {'active': _('Active'), 'deactivated': _('Deactivated'), 'revoked': _('Revoked'),
            'expired': _('Expired'), 'inactive': _('Inactive')}[status]


def card_data(card, lang, public=False):
    """Everything a face needs, already localised and privacy-filtered by the card's display options."""
    from clinic.models import ClinicProfile
    from .models import IDCardBranding
    h, user = card.holder, card.holder.user
    clinic, brand = ClinicProfile.objects.first(), IDCardBranding.get()
    with translation.override(lang):
        fmt = lambda d: date_format(d, 'DATE_FORMAT') if d else ''
        data = {
            'lang': lang, 'rtl': lang == 'ar', 'brand': brand,
            'org': clinic.name if clinic else 'SpinalCure', 'tagline': brand.tagline or (clinic.tagline if clinic else ''),
            'address': (clinic.address if clinic else ''), 'org_phone': (clinic.phone if clinic else ''),
            'org_email': (clinic.email if clinic else ''), 'website': brand.org_url or (clinic.website if clinic else ''),
            'logo': clinic.logo.path if clinic and clinic.logo and Path(clinic.logo.path).exists() else None,
            'name': user.get_full_name() or user.username, 'photo': user.photo.path if user.photo and Path(user.photo.path).exists() else None,
            'employee_id': h.employee_id, 'card_type': card.get_card_type_display(), 'type_key': card.card_type,
            'designation': h.designation, 'department': h.department,
            'phone': (h.contact_phone or user.phone) if card.show_phone else '',
            'email': (h.contact_email or user.email) if card.show_email else '',
            'joined': fmt(h.joined_on), 'issued': fmt(card.issued_on), 'expires': fmt(card.expires_on),
            'status': card.effective_status, 'status_label': status_label(card.effective_status),
            'card_id': card.display_id,
            'emergency': (h.emergency_contact_name, h.emergency_contact_phone) if card.show_emergency_contact and h.emergency_contact_name else None,
            'blood': h.blood_group if card.show_blood_group else '', 'skills': h.skills if card.show_skills else '',
            'labels': {
                'employee_id': _('Owner ID') if card.card_type == 'owner' else _('Staff ID'),
                'department': _('Department'), 'phone': _('Phone'), 'email': _('Email'), 'joined': _('Joined'),
                'issued': _('Issued'), 'valid_until': _('Valid until'), 'scan': _('Scan to verify'),
                'about': _('About the organisation'), 'emergency': _('Emergency contact'), 'blood': _('Blood group'),
                'skills': _('Skills'), 'card_id': _('Card ID'), 'tel': _('Tel'),
            },
            'footer': brand.legal_footer,
        }
    if public:   # share image / link previews: identity + authenticity only, never contact or personal details
        data.update(phone='', email='', emergency=None, blood='', skills='')
    return data


def render_face(card, side, verify_url, org_url, scale=1, lang='en', public=False):
    """PIL image of 'front' or 'back'. Base size 900x560 px, multiplied by `scale` (3 gives 2700x1680)."""
    d = card_data(card, lang, public)
    with translation.override(lang):
        return _front(d, verify_url, scale) if side == 'front' else _back(d, verify_url, org_url, scale)


def _front(d, verify_url, s):
    W, H = BASE_W * s, BASE_H * s
    primary, accent = hex_rgb(d['brand'].primary_color), hex_rgb(d['brand'].accent_color, (22, 163, 74))
    img = Image.new('RGB', (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(img)
    rtl = d['rtl']
    X = (lambda x: W - x * s) if rtl else (lambda x: x * s)        # mirrors anchors for RTL
    align = 'right' if rtl else 'left'
    dr.rectangle((0, 0, W, 110 * s), fill=primary)
    # logo / initial
    lx = (W - (36 + 64) * s) if rtl else 36 * s
    if d['logo']:
        _rounded_paste(img, Image.open(d['logo']), (lx, 23 * s, lx + 64 * s, 87 * s), 12 * s)
    else:
        dr.ellipse((lx, 23 * s, lx + 64 * s, 87 * s), fill=(255, 255, 255))
        draw_text(dr, lx + 32 * s, 32 * s, (d['org'] or 'S')[:1], 40 * s, primary, True, 'center')
    tx = X(120)
    draw_text(dr, tx, 24 * s, d['org'], 32 * s, (255, 255, 255), True, align, max_w=520 * s, rtl=rtl)
    if d['tagline']:
        draw_text(dr, tx, 66 * s, d['tagline'], 20 * s, (220, 235, 225), False, align, max_w=520 * s, rtl=rtl)
    # type pill
    pill_w = int(text_width(d['card_type'].upper() if d['lang'] != 'ar' else d['card_type'], 22 * s, True)) + 36 * s
    px0 = 36 * s if rtl else W - 36 * s - pill_w
    dr.rounded_rectangle((px0, 36 * s, px0 + pill_w, 74 * s), 19 * s, fill=accent)
    draw_text(dr, px0 + pill_w / 2, 42 * s, d['card_type'].upper() if d['lang'] != 'ar' else d['card_type'],
              22 * s, (255, 255, 255), True, 'center')
    # photo
    ph = (W - 36 * s - 200 * s, 140 * s, W - 36 * s, 390 * s) if rtl else (36 * s, 140 * s, 236 * s, 390 * s)
    if d['photo']:
        _rounded_paste(img, Image.open(d['photo']), ph, 18 * s)
    else:
        dr.rounded_rectangle(ph, 18 * s, fill=(236, 253, 245))
        draw_text(dr, (ph[0] + ph[2]) / 2, ph[1] + 70 * s, (d['name'] or '?')[:1].upper(), 110 * s, primary, True, 'center')
    # identity
    text_max = (W - 36 * s) - 270 * s if not rtl else (W - 270 * s) - 36 * s
    draw_text(dr, X(268), 150 * s, d['name'], 40 * s, (17, 24, 39), True, align, max_w=text_max, rtl=rtl)
    badge = f"{d['employee_id']}"
    bw = int(text_width(badge, 24 * s, True)) + 32 * s
    bx = W - 268 * s - bw if rtl else 268 * s
    dr.rounded_rectangle((bx, 212 * s, bx + bw, 250 * s), 10 * s, fill=(240, 253, 244), outline=accent, width=2 * s)
    draw_text(dr, bx + bw / 2, 216 * s, badge, 24 * s, primary, True, 'center')
    draw_text(dr, X(268), 268 * s, d['designation'], 28 * s, (31, 41, 55), True, align, max_w=text_max, rtl=rtl)
    y = 306 * s
    grey, dark = (107, 114, 128), (31, 41, 55)
    for key in ('department', 'phone', 'email'):
        if d[key]:
            draw_pair(dr, X(268), y, d['labels'][key], d[key], 22 * s, grey, dark, rtl, max_w=400 * s)
            y += 34 * s
    # QR (kept clear of the footer rule so it scans cleanly)
    q = 156 * s
    qx = 36 * s if rtl else W - 36 * s - q
    img.paste(qr_image(verify_url, q), (qx, 296 * s))
    draw_text(dr, qx + q / 2, 296 * s + q + 4 * s, d['labels']['scan'], 18 * s, (75, 85, 99), False, 'center')
    # footer
    dr.line((36 * s, 492 * s, W - 36 * s, 492 * s), fill=(229, 231, 235), width=s)
    sc = STATUS_COLORS.get(d['status'], (107, 114, 128))
    sw = int(text_width(d['status_label'], 20 * s, True)) + 28 * s
    sx = W - 36 * s - sw if rtl else 36 * s
    dr.rounded_rectangle((sx, 506 * s, sx + sw, 540 * s), 17 * s, fill=sc)
    draw_text(dr, sx + sw / 2, 510 * s, d['status_label'], 20 * s, (255, 255, 255), True, 'center')
    mx = sx - 20 * s if rtl else sx + sw + 20 * s
    draw_pair(dr, mx, 511 * s, d['labels']['joined'], d['joined'], 20 * s, grey, (75, 85, 99), rtl, max_w=300 * s)
    if d['expires']:
        mx2 = (mx - 330 * s) if rtl else (mx + 330 * s)
        draw_pair(dr, mx2, 511 * s, d['labels']['valid_until'], d['expires'], 20 * s, grey, (75, 85, 99), rtl,
                  max_w=260 * s)
    return img


def _back(d, verify_url, org_url, s):
    W, H = BASE_W * s, BASE_H * s
    primary, accent = hex_rgb(d['brand'].primary_color), hex_rgb(d['brand'].accent_color, (22, 163, 74))
    img = Image.new('RGB', (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(img)
    rtl = d['rtl']
    X = (lambda x: W - x * s) if rtl else (lambda x: x * s)
    align = 'right' if rtl else 'left'
    dr.rectangle((0, 0, W, 56 * s), fill=primary)
    draw_text(dr, X(36), 10 * s, d['org'], 28 * s, (255, 255, 255), True, align, max_w=820 * s, rtl=rtl)
    grey, dark = (107, 114, 128), (31, 41, 55)
    y = 74 * s
    draw_text(dr, X(36), y, d['labels']['about'], 17 * s, accent, True, align, rtl=rtl)
    y += 26 * s
    for line in wrap(d['address'], 20 * s, 520 * s, 3):
        draw_text(dr, X(36), y, line, 20 * s, dark, False, align, rtl=rtl)
        y += 26 * s
    for val in (d['org_phone'], d['org_email'], d['website']):
        if val:
            draw_text(dr, X(36), y, val, 20 * s, dark, False, align, max_w=520 * s, rtl=rtl)
            y += 26 * s
    y += 8 * s
    if d['emergency']:
        draw_text(dr, X(36), y, d['labels']['emergency'], 17 * s, accent, True, align, rtl=rtl)
        y += 24 * s
        name, phone = d['emergency']
        draw_pair(dr, X(36), y, '', name, 20 * s, grey, dark, rtl, max_w=300 * s)
        if phone:
            draw_text(dr, X(36 + 320), y, phone, 20 * s, dark, False, align, max_w=230 * s)
        y += 30 * s
    for key in ('blood', 'skills'):
        if d[key]:
            draw_pair(dr, X(36), y, d['labels'][key], d[key], 20 * s, grey, dark, rtl, max_w=520 * s)
            y += 26 * s
    # issue info (anchored low so it never collides with the flowing content above)
    draw_pair(dr, X(36), 396 * s, d['labels']['card_id'], d['card_id'], 21 * s, grey, dark, rtl, bold_value=True)
    draw_pair(dr, X(36), 428 * s, d['labels']['issued'], d['issued'], 19 * s, grey, (75, 85, 99), rtl, max_w=280 * s)
    if d['expires']:
        draw_pair(dr, X(36 + 300), 428 * s, d['labels']['valid_until'], d['expires'], 19 * s, grey, (75, 85, 99), rtl,
                  max_w=260 * s)
    # org QR
    q = 150 * s
    qx = 36 * s if rtl else W - 36 * s - q
    img.paste(qr_image(org_url or verify_url, q), (qx, 100 * s))
    draw_text(dr, qx + q / 2, 100 * s + q + 4 * s, d['labels']['about'], 16 * s, (75, 85, 99), False, 'center', max_w=q + 40 * s)
    # legal footer
    dr.line((36 * s, 466 * s, W - 36 * s, 466 * s), fill=(229, 231, 235), width=s)
    for i, line in enumerate(wrap(d['footer'], 17 * s, W - 72 * s, 3)):
        draw_text(dr, X(36), 478 * s + i * 24 * s, line, 17 * s, (107, 114, 128), False, align, rtl=rtl)
    return img


def to_png_bytes(img):
    out = io.BytesIO()
    img.save(out, 'PNG', optimize=True)
    return out.getvalue()


def to_pdf_bytes(front, back):
    """Two landscape pages (front, back), each page exactly the card face."""
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    pw, ph = BASE_W * 0.75, BASE_H * 0.75
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=(pw, ph))
    c.setTitle('ID card')
    for face in (front, back):
        c.drawImage(ImageReader(face), 0, 0, pw, ph)
        c.showPage()
    c.save()
    return out.getvalue()
