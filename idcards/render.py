"""
Server-side rendering of ID card faces with Pillow (RAQM shaping) and the bundled Noto fonts.

Used for: the public share image / Open Graph preview, and the PNG/PDF download fallbacks. The interactive
card in the browser is HTML; this produces the same information with the same branding.

Each text is split into runs by script and drawn with a font that has those glyphs (the Noto script fonts
carry no Latin letters or punctuation). For right-to-left text runs are laid out in visual order.
"""
import io
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import qrcode
from django.conf import settings
from django.utils import translation
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from PIL import Image, ImageDraw, ImageFont, ImageOps

BASE_W, BASE_H = 560, 900          # vertical card
FONT_DIR = Path(settings.BASE_DIR) / 'static' / 'fonts'
RAQM = ImageFont.Layout.RAQM

SCRIPT_FONT = {'latin': 'NotoSans', 'tamil': 'NotoSansTamil', 'deva': 'NotoSansDevanagari', 'arabic': 'NotoSansArabic',
               'telugu': 'NotoSansTelugu', 'kannada': 'NotoSansKannada', 'malayalam': 'NotoSansMalayalam'}


def _script(ch):
    cp = ord(ch)
    if 0x0B80 <= cp <= 0x0BFF:
        return 'tamil'
    if 0x0900 <= cp <= 0x097F:
        return 'deva'
    if 0x0C00 <= cp <= 0x0C7F:
        return 'telugu'
    if 0x0C80 <= cp <= 0x0CFF:
        return 'kannada'
    if 0x0D00 <= cp <= 0x0D7F:
        return 'malayalam'
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


from PIL import features as _pil_features

_RAQM = _pil_features.check('raqm')


def _dir(script):
    """Text-direction kwargs; Pillow only accepts them when built with libraqm (else basic layout, no shaping)."""
    return {'direction': 'rtl' if script == 'arabic' else 'ltr'} if _RAQM else {}


def text_width(text, px, bold=False):
    return sum(_font(sc, bold, px).getlength(run, **_dir(sc)) for sc, run in _runs(text))


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
        draw.text((cx, baseline), run, font=font, fill=fill, anchor='ls', **_dir(sc))
        cx += font.getlength(run, **_dir(sc))
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


def _featured_quote(clinic, lang):
    """The clinic's Featured Quote (Clinic Settings), in the card's language when a translation exists."""
    if not clinic:
        return ''
    from clinic.content_i18n import tx
    return tx(clinic, 'about_quote', lang) or ''


def split_lines(text, parts=None):
    """Break after commas: "A, B, C." -> ["A,", "B,", "C."]; `parts` limits how many lines (the rest stays on the last)."""
    pieces = [x.strip() for x in re.split(r'(?<=,)\s+', (text or '').strip()) if x.strip()]
    if parts and len(pieces) > parts:
        pieces = pieces[:parts - 1] + [' '.join(pieces[parts - 1:])]
    return pieces


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
            'tagline_lines': split_lines(brand.tagline or (clinic.tagline if clinic else ''), 2),
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
            'gender': str(dict(h.GENDER_CHOICES).get(h.gender, '')),
            'dob': fmt(h.date_of_birth), 'home_address': h.address,
            'quote': split_lines(_featured_quote(clinic, lang)) or [_('Without Surgery,'), _('Without Medicine'), _('and Without Diet')],
            'labels': {
                'employee_id': _('Owner ID') if card.card_type == 'owner' else _('Staff ID'),
                'department': _('Department'), 'phone': _('Phone'), 'email': _('Email'), 'joined': _('Joined'),
                'issued': _('Issued'), 'valid_until': _('Valid until'), 'scan': _('Scan to verify'),
                'about': _('About the organisation'), 'emergency': _('Emergency contact'), 'blood': _('Blood group'),
                'skills': _('Skills'), 'card_id': _('Card ID'), 'tel': _('Tel'),
                'gender': _('Gender'), 'dob': _('Date of birth'), 'home': _('Address'), 'clinic': _('Clinic'),
                'site': _('Our website'),
            },
            'footer': brand.legal_footer,
        }
    if public:   # share image / link previews: identity + authenticity only, never contact or personal details
        data.update(phone='', email='', emergency=None, blood='', skills='', gender='', dob='', home_address='')
    return data


def render_face(card, side, verify_url, org_url, scale=1, lang='en', public=False):
    """PIL image of 'front' or 'back'. Base size 900x560 px, multiplied by `scale` (3 gives 2700x1680)."""
    d = card_data(card, lang, public)
    with translation.override(lang):
        return _front(d, verify_url, scale) if side == 'front' else _back(d, verify_url, org_url, scale)


def yin_yang(size, dark, light=(255, 255, 255)):
    """Yin-yang emblem as an RGBA image of `size` px (drawn at 4x and downsampled for smooth edges)."""
    S = size * 4
    im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r, c = S // 2, S // 2
    d.ellipse((0, 0, S - 1, S - 1), fill=light + (255,))
    d.pieslice((0, 0, S - 1, S - 1), 270, 90, fill=dark + (255,))                 # right half dark
    d.ellipse((c - r // 2, 0, c + r // 2, r), fill=light + (255,))                # top bulb light
    d.ellipse((c - r // 2, r, c + r // 2, S - 1), fill=dark + (255,))             # bottom bulb dark
    dot = r // 6
    d.ellipse((c - dot, r // 2 - dot, c + dot, r // 2 + dot), fill=dark + (255,))
    d.ellipse((c - dot, 3 * r // 2 - dot, c + dot, 3 * r // 2 + dot), fill=light + (255,))
    d.ellipse((0, 0, S - 1, S - 1), outline=dark + (255,), width=max(2, S // 40))
    return im.resize((size, size), Image.LANCZOS)


def _field(dr, x, y, label, value, s, grey, dark, rtl, w):
    """Small grey label above a bold value (one detail cell)."""
    if not value:
        return
    align = 'right' if rtl else 'left'
    draw_text(dr, x, y, label, 14 * s, grey, False, align, max_w=w, rtl=rtl)
    draw_text(dr, x, y + 19 * s, value, 19 * s, dark, True, align, max_w=w, rtl=rtl)


def _front(d, verify_url, s):
    """Identity side: photo, name, role, gender, date of birth, blood group, phone, home address, verify QR."""
    W, H = BASE_W * s, BASE_H * s
    primary, accent = hex_rgb(d['brand'].primary_color), hex_rgb(d['brand'].accent_color, (22, 163, 74))
    grey, dark = (107, 114, 128), (31, 41, 55)
    img = Image.new('RGB', (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(img)
    rtl = d['rtl']
    X = (lambda x: W - x * s) if rtl else (lambda x: x * s)
    align = 'right' if rtl else 'left'
    dr.rectangle((0, 0, W, 128 * s), fill=primary)
    lx = (W - (36 + 72) * s) if rtl else 36 * s
    if d['logo']:
        _rounded_paste(img, Image.open(d['logo']), (lx, 28 * s, lx + 72 * s, 100 * s), 14 * s)
    else:
        dr.ellipse((lx, 28 * s, lx + 72 * s, 100 * s), fill=(255, 255, 255))
        draw_text(dr, lx + 36 * s, 38 * s, (d['org'] or 'S')[:1], 44 * s, primary, True, 'center')
    draw_text(dr, X(124), 22 * s, d['org'], 30 * s, (255, 255, 255), True, align, max_w=400 * s, rtl=rtl)
    for i, line in enumerate(d['tagline_lines']):
        draw_text(dr, X(124), (62 + i * 22) * s, line, 16 * s, (220, 235, 225), False, align, max_w=400 * s, rtl=rtl)
    # photo with accent ring
    pw, ph, px, py = 220 * s, 260 * s, (W - 220 * s) // 2, 150 * s
    dr.rounded_rectangle((px - 7 * s, py - 7 * s, px + pw + 7 * s, py + ph + 7 * s), 26 * s, outline=accent, width=4 * s)
    if d['photo']:
        _rounded_paste(img, Image.open(d['photo']), (px, py, px + pw, py + ph), 20 * s)
    else:
        dr.rounded_rectangle((px, py, px + pw, py + ph), 20 * s, fill=(236, 253, 245))
        draw_text(dr, W / 2, py + 70 * s, (d['name'] or '?')[:1].upper(), 120 * s, primary, True, 'center')
    # identity
    draw_text(dr, W / 2, 428 * s, d['name'], 34 * s, (17, 24, 39), True, 'center', max_w=488 * s)
    draw_text(dr, W / 2, 472 * s, d['designation'], 21 * s, dark, False, 'center', max_w=488 * s)
    badge, ptxt = d['employee_id'], (d['card_type'].upper() if d['lang'] != 'ar' else d['card_type'])
    bw, pw2 = int(text_width(badge, 20 * s, True)) + 28 * s, int(text_width(ptxt, 17 * s, True)) + 28 * s
    gap = 12 * s
    bx = (W - (bw + gap + pw2)) // 2
    dr.rounded_rectangle((bx, 508 * s, bx + bw, 544 * s), 10 * s, fill=(240, 253, 244), outline=accent, width=2 * s)
    draw_text(dr, bx + bw / 2, 514 * s, badge, 20 * s, primary, True, 'center')
    dr.rounded_rectangle((bx + bw + gap, 508 * s, bx + bw + gap + pw2, 544 * s), 18 * s, fill=accent)
    draw_text(dr, bx + bw + gap + pw2 / 2, 516 * s, ptxt, 17 * s, (255, 255, 255), True, 'center')
    # details (two columns + QR)
    L = d['labels']
    c1, c2 = X(36), X(188)
    _field(dr, c1, 574 * s, L['gender'], d['gender'], s, grey, dark, rtl, 140 * s)
    _field(dr, c2, 574 * s, L['dob'], d['dob'], s, grey, dark, rtl, 200 * s)
    _field(dr, c1, 634 * s, L['blood'], d['blood'], s, grey, dark, rtl, 140 * s)
    _field(dr, c2, 634 * s, L['phone'], d['phone'], s, grey, dark, rtl, 200 * s)
    q = 112 * s
    qx = 36 * s if rtl else W - 36 * s - q
    img.paste(qr_image(verify_url, q), (qx, 570 * s))
    draw_text(dr, qx + q / 2, 570 * s + q + 2 * s, L['scan'], 14 * s, (75, 85, 99), False, 'center', max_w=q + 30 * s)
    if d['home_address']:
        draw_text(dr, X(36), 716 * s, L['home'], 14 * s, grey, False, align, rtl=rtl)
        for i, line in enumerate(wrap(d['home_address'].replace('\n', ' '), 17 * s, 488 * s, 3, True)):
            draw_text(dr, X(36), (736 + i * 21) * s, line, 17 * s, dark, True, align, rtl=rtl)
    # footer
    dr.line((36 * s, 808 * s, W - 36 * s, 808 * s), fill=(229, 231, 235), width=s)
    sc = STATUS_COLORS.get(d['status'], (107, 114, 128))
    sw = int(text_width(d['status_label'], 17 * s, True)) + 26 * s
    sx = W - 36 * s - sw if rtl else 36 * s
    dr.rounded_rectangle((sx, 824 * s, sx + sw, 854 * s), 15 * s, fill=sc)
    draw_text(dr, sx + sw / 2, 828 * s, d['status_label'], 17 * s, (255, 255, 255), True, 'center')
    mx = sx - 16 * s if rtl else sx + sw + 16 * s
    draw_pair(dr, mx, 829 * s, L['joined'], d['joined'], 16 * s, grey, (75, 85, 99), rtl, max_w=190 * s)
    return img


def _back(d, verify_url, org_url, s):
    """Clinic side: yin-yang, the clinic's promise, clinic address/contact/website, QR, card id and validity."""
    W, H = BASE_W * s, BASE_H * s
    primary, accent = hex_rgb(d['brand'].primary_color), hex_rgb(d['brand'].accent_color, (22, 163, 74))
    grey, dark = (107, 114, 128), (31, 41, 55)
    img = Image.new('RGB', (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(img)
    rtl = d['rtl']
    X = (lambda x: W - x * s) if rtl else (lambda x: x * s)
    align = 'right' if rtl else 'left'
    L = d['labels']
    dr.rectangle((0, 0, W, 122 * s), fill=primary)
    draw_text(dr, W / 2, 20 * s, d['org'], 30 * s, (255, 255, 255), True, 'center', max_w=488 * s)
    for i, line in enumerate(d['tagline_lines']):
        draw_text(dr, W / 2, (62 + i * 22) * s, line, 16 * s, (220, 235, 225), False, 'center', max_w=488 * s)
    # yin-yang on a soft disc
    cx, cy, R = W // 2, 230 * s, 100 * s
    dr.ellipse((cx - R, cy - R, cx + R, cy + R), fill=(236, 253, 245))
    ys = 160 * s
    emblem = yin_yang(ys, primary)
    img.paste(emblem, (cx - ys // 2, cy - ys // 2), emblem)
    # the clinic's promise
    for i, line in enumerate(d['quote']):
        draw_text(dr, W / 2, (350 + i * 38) * s, line, 27 * s, primary, True, 'center', max_w=488 * s)
    dr.rounded_rectangle((W // 2 - 30 * s, 470 * s, W // 2 + 30 * s, 474 * s), 2 * s, fill=accent)
    # clinic contact + website QR
    y = 492 * s
    draw_text(dr, X(36), y, L['clinic'], 14 * s, accent, True, align, rtl=rtl)
    y += 24 * s
    for line in wrap(d['address'], 16 * s, 350 * s, 4):
        draw_text(dr, X(36), y, line, 16 * s, dark, False, align, rtl=rtl)
        y += 22 * s
    for val in (d['org_phone'], d['org_email'], d['website']):
        if val:
            draw_text(dr, X(36), y, val, 16 * s, dark, False, align, max_w=350 * s, rtl=rtl)
            y += 22 * s
    q = 112 * s
    qx = 36 * s if rtl else W - 36 * s - q
    img.paste(qr_image(org_url or verify_url, q), (qx, 492 * s))
    draw_text(dr, qx + q / 2, 492 * s + q + 2 * s, L['site'], 14 * s, (75, 85, 99), False, 'center', max_w=q + 30 * s)
    # card id and validity
    draw_pair(dr, X(36), 706 * s, L['card_id'], d['card_id'], 20 * s, grey, dark, rtl, bold_value=True)
    draw_pair(dr, X(36), 738 * s, L['issued'], d['issued'], 17 * s, grey, (75, 85, 99), rtl, max_w=240 * s)
    if d['expires']:
        draw_pair(dr, X(36 + 250), 738 * s, L['valid_until'], d['expires'], 17 * s, grey, (75, 85, 99), rtl, max_w=240 * s)
    # legal footer
    dr.line((36 * s, 786 * s, W - 36 * s, 786 * s), fill=(229, 231, 235), width=s)
    for i, line in enumerate(wrap(d['footer'], 15 * s, W - 72 * s, 4)):
        draw_text(dr, X(36), (798 + i * 21) * s, line, 15 * s, (107, 114, 128), False, align, rtl=rtl)
    return img


def to_png_bytes(img):
    out = io.BytesIO()
    img.save(out, 'PNG', optimize=True)
    return out.getvalue()


def to_pdf_bytes(front, back):
    """Two portrait pages (front, back), each page exactly the card face."""
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    pw, ph = BASE_W * 0.75, BASE_H * 0.75     # portrait pages
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=(pw, ph))
    c.setTitle('ID card')
    for face in (front, back):
        c.drawImage(ImageReader(face), 0, 0, pw, ph)
        c.showPage()
    c.save()
    return out.getvalue()
