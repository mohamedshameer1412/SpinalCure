"""
Real-browser checks of the interactive ID card (Chromium via Playwright, against a live server).
External hosts are blocked, so the card must work entirely from its vendored CSS/JS/fonts.
"""
import io
import os
import re
from datetime import date

import numpy as np
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from PIL import Image
from pypdf import PdfReader

pw = pytest.importorskip('playwright.sync_api')
CHROMIUM = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
pytestmark = [pytest.mark.skipif(not os.path.exists(CHROMIUM), reason='Chromium not installed'),
              pytest.mark.django_db(transaction=True)]

User = get_user_model()


@pytest.fixture
def seeded(settings, db):
    from accounts.models import StaffProfile
    from clinic.models import ClinicProfile
    from idcards import service
    settings.SITE_URL = 'https://clinic.example'
    clinic = ClinicProfile.objects.create(name='Test Clinic', address='12 Anna Salai, Chennai', phone='9876543210',
                                          email='care@clinic.example', website='https://clinic.example')
    boss = User.objects.create_user(username='boss', email='boss@example.com', password='x', role='owner')
    user = User.objects.create_user(username='priya', email='priya@example.com', password='x', role='staff',
                                    first_name='பிரியா', last_name='நடராஜன்', phone='+91 98765 43210')
    profile = StaffProfile.objects.create(user=user, clinic=clinic, designation='Physiotherapist', department='Rehab',
                                          joined_on=date(2024, 3, 12))
    card = service.issue(profile, boss, show_email=True)
    return user, card


@pytest.fixture
def browser_ctx(live_server, seeded):
    user, card = seeded
    client = Client(); client.force_login(user)
    sid = client.cookies['sessionid'].value
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM, args=['--no-sandbox'])
        ctx = browser.new_context(viewport={'width': 1200, 'height': 900}, accept_downloads=True,
                                  permissions=['clipboard-read', 'clipboard-write'])
        ctx.add_cookies([{'name': 'sessionid', 'value': sid, 'url': live_server.url}])
        host = live_server.url.split('//')[1]
        ctx.route('**/*', lambda route: route.continue_() if route.request.url.split('/')[2] == host else route.abort())
        yield ctx, live_server.url, card
        browser.close()


def open_card(browser_ctx, query=''):
    ctx, base, card = browser_ctx
    page = ctx.new_page()
    errors = []
    # base.html pulls Tailwind/Alpine/htmx from CDNs, which this sandbox blocks; ignore only those, never the card's own errors
    third_party = ('tailwind', 'Alpine', 'htmx', 'TomSelect', 'Chart is not defined')
    page.on('pageerror', lambda e: None if any(t in str(e) for t in third_party) else errors.append(str(e)))
    page.goto(f'{base}/en/idcards/mine/{query}', wait_until='domcontentloaded')
    page.wait_for_selector('[data-idc-root][data-idc-ready="1"]')
    page.evaluate('document.fonts.ready')
    return page, errors, card


def computed(page, selector, prop):
    return page.evaluate(f"getComputedStyle(document.querySelector('{selector}')).{prop}")


def test_page_loads_without_script_errors_and_uses_specified_flip_css(browser_ctx):
    page, errors, _card = open_card(browser_ctx)
    assert errors == []
    assert computed(page, '.idc-flip', 'perspective') == '1600px'
    assert computed(page, '.idc-inner', 'transitionDuration') == '0.8s'
    assert computed(page, '.idc-inner', 'transitionTimingFunction') == 'cubic-bezier(0.4, 0, 0.2, 1)'
    assert computed(page, '.idc-inner', 'transformStyle') == 'preserve-3d'
    assert computed(page, '.idc-face', 'backfaceVisibility') == 'hidden'


def test_click_flips_with_rotateY_180_and_back(browser_ctx):
    page, _e, _c = open_card(browser_ctx)
    flip = page.locator('.idc-flip')
    assert flip.get_attribute('aria-pressed') == 'false'
    flip.click()
    page.wait_for_timeout(1000)                                         # 0.8s transition
    assert flip.get_attribute('aria-pressed') == 'true' and 'is-flipped' in flip.get_attribute('class')
    inner = re.search(r'\((.*)\)', computed(page, '.idc-inner', 'transform')).group(1)       # args of matrix3d(...)
    m = [float(x) for x in inner.split(',')]
    assert len(m) == 16 and abs(m[0] + 1) < 1e-3 and abs(m[10] + 1) < 1e-3   # rotateY(180deg): cos(180deg) = -1 on both axes
    assert 'back side' in flip.get_attribute('aria-label')
    flip.click(); page.wait_for_timeout(1000)
    assert flip.get_attribute('aria-pressed') == 'false'


def test_keyboard_flip_with_enter_and_space_and_visible_focus(browser_ctx):
    page, _e, _c = open_card(browser_ctx)
    flip = page.locator('.idc-flip')
    flip.focus()
    assert page.evaluate("document.activeElement.classList.contains('idc-flip')")
    page.keyboard.press('Enter'); page.wait_for_timeout(100)
    assert flip.get_attribute('aria-pressed') == 'true'
    page.keyboard.press(' '); page.wait_for_timeout(100)
    assert flip.get_attribute('aria-pressed') == 'false'
    assert flip.get_attribute('role') == 'button' and flip.get_attribute('tabindex') == '0'
    page.locator('[data-idc-flip]').click(); page.wait_for_timeout(100)    # the explicit button works too
    assert flip.get_attribute('aria-pressed') == 'true'


def test_reduced_motion_disables_the_flip_animation(browser_ctx):
    page, _e, _c = open_card(browser_ctx)
    page.emulate_media(reduced_motion='reduce')
    assert computed(page, '.idc-inner', 'transitionDuration') == '0s'
    page.locator('.idc-flip').click()
    assert page.locator('.idc-flip').get_attribute('aria-pressed') == 'true'      # still flips, instantly


def test_resize_observer_scales_card_to_container_without_horizontal_overflow(browser_ctx):
    page, _e, _c = open_card(browser_ctx)
    def scale():
        return float(re.search(r'matrix\(([\d.]+)', computed(page, '.idc-scale', 'transform')).group(1))
    assert abs(scale() - 1.0) < 0.01                                     # wide screen: natural size
    page.set_viewport_size({'width': 390, 'height': 800}); page.wait_for_timeout(300)
    k = scale()
    assert 0.3 < k < 0.45
    stage_h = page.evaluate("document.querySelector('.idc-stage').getBoundingClientRect().height")
    assert abs(stage_h - 560 * k) < 3                                    # no layout jump or dead space
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')   # no horizontal overflow
    page.set_viewport_size({'width': 700, 'height': 800}); page.wait_for_timeout(300)
    assert 0.6 < scale() < 0.85                                          # follows continuous resizing


def test_toolbar_buttons_are_touch_sized(browser_ctx):
    page, _e, _c = open_card(browser_ctx)
    heights = page.evaluate("[...document.querySelectorAll('.idc-toolbar button')].map(b => b.getBoundingClientRect().height)")
    assert len(heights) == 7 and min(heights) >= 44


def test_png_export_is_exactly_2700x1680_for_both_faces(browser_ctx):
    page, errors, card = open_card(browser_ctx)
    for side, label in (('front', 'Download front (PNG)'), ('back', 'Download back (PNG)')):
        with page.expect_download(timeout=30000) as dl:
            page.get_by_role('button', name=label).click()
        path = dl.value.path()
        img = Image.open(path)
        assert img.size == (2700, 1680), (side, img.size)
        arr = np.array(img.convert('L'))
        assert arr.std() > 20                                            # not blank
        assert dl.value.suggested_filename == f'{card.holder.employee_id}-{side}.png'
    assert errors == []
    # resource cleanup: html2canvas's temporary clone frame is gone and no bitmap canvas is left in the DOM
    assert page.evaluate("document.querySelectorAll('iframe').length") == 0
    assert page.evaluate("document.querySelectorAll('canvas').length") == 0


def test_export_captures_the_face_even_when_card_is_flipped_or_scaled_down(browser_ctx):
    page, _e, _c = open_card(browser_ctx)
    page.set_viewport_size({'width': 390, 'height': 800}); page.wait_for_timeout(300)
    page.locator('.idc-flip').click(); page.wait_for_timeout(900)          # flipped to the back AND scaled to ~0.4
    with page.expect_download(timeout=30000) as dl:
        page.get_by_role('button', name='Download front (PNG)').click()
    img = Image.open(dl.value.path())
    assert img.size == (2700, 1680)
    header = np.array(img.convert('RGB'))[30:60, 1000:1200].reshape(-1, 3).mean(axis=0)
    assert abs(header[0] - 22) < 12 and abs(header[1] - 101) < 12            # the front's green header, not a mirrored back


def test_pdf_export_has_two_portrait_pages_front_then_back(browser_ctx):
    page, errors, card = open_card(browser_ctx)
    with page.expect_download(timeout=40000) as dl:
        page.get_by_role('button', name='Download PDF').click()
    reader = PdfReader(dl.value.path())
    assert len(reader.pages) == 2 and errors == []
    drawn = []
    for pg in reader.pages:
        w, h = float(pg.mediabox.width), float(pg.mediabox.height)
        assert w < h and abs(w / h - 560 / 900) < 0.02
        # jsPDF lists every image in a shared resource dictionary; what matters is which one each page DRAWS
        names = re.findall(rb'/(\w+) Do', pg.get_contents().get_data())
        assert len(names) == 1, names                                                      # exactly one face per page
        drawn.append(names[0])
    assert drawn[0] != drawn[1]                                                             # front and back are different images
    faces = {name.decode(): np.array(Image.open(io.BytesIO(img.data)).convert('L')) for pg in reader.pages for img in pg.images
             for name in [img.name.split('.')[0].encode()]}
    sizes = {a.shape for a in faces.values()}
    assert all(w >= 2000 for (_h, w) in sizes)                                              # exported at 3x, not screen resolution
    assert dl.value.suggested_filename == f'{card.holder.employee_id}.pdf'


def test_tamil_name_renders_in_export_with_bundled_font(browser_ctx):
    page, _e, _c = open_card(browser_ctx, '?lang=ta')
    assert page.evaluate("document.fonts.check('700 40px \"IDC Tamil\"', 'பிரியா')")
    loaded = page.evaluate("[...document.fonts].filter(f => f.status === 'loaded').map(f => f.family)")
    assert any('IDC Tamil' in f for f in loaded)
    with page.expect_download(timeout=30000) as dl:
        page.get_by_role('button', name=re.compile('PNG')).first.click()
    img = Image.open(dl.value.path()).convert('L')
    band = np.array(img.crop((804, 450, 2600, 620)))                     # the name area at 3x
    assert (band < 128).sum() > 3000                                     # glyphs drawn, not blank or .notdef boxes only
    # Real shaping, not boxes: .notdef boxes are identical squares; distinct letters give distinct column profiles
    cols = (band < 128).sum(axis=0)
    assert len(set(cols[cols > 0].tolist())) > 25


def test_arabic_layout_is_mirrored_and_ids_stay_left_to_right(browser_ctx):
    page, _e, _c = open_card(browser_ctx, '?lang=ar')
    art = page.locator('.idc-flip .idc-art').first
    assert art.get_attribute('dir') == 'rtl'
    photo = page.evaluate("document.querySelector('.idc-flip .idc-photo').getBoundingClientRect().left")
    qr = page.evaluate("document.querySelector('.idc-flip .idc-qr').getBoundingClientRect().left")
    card_left = page.evaluate("document.querySelector('.idc-flip').getBoundingClientRect().left")
    assert photo - card_left > 450 and qr - card_left < 100              # photo on the right, QR on the left
    for sel in ('.idc-flip .idc-badge', '.idc-flip .idc-line .idc-num'):
        assert computed(page, sel, 'direction') == 'ltr' and computed(page, sel, 'unicodeBidi') == 'isolate'
    assert page.evaluate("document.querySelector('.idc-stage').dir || getComputedStyle(document.querySelector('.idc-stage')).direction") in ('ltr',)


def test_share_uses_native_api_when_present_and_copies_link_otherwise(browser_ctx):
    page, _e, card = open_card(browser_ctx)
    verify = f'https://clinic.example/verify/{card.card_id}/'
    page.evaluate("Object.defineProperty(navigator, 'share', {value: undefined, configurable: true}); Object.defineProperty(navigator, 'canShare', {value: undefined, configurable: true})")
    page.get_by_role('button', name='Share').click(); page.wait_for_timeout(300)
    assert page.evaluate('navigator.clipboard.readText()') == verify       # safe fallback: copy the verification link
    assert 'copied' in page.locator('.idc-toast').first.inner_text().lower()
    page.evaluate("window.__shared = null; Object.defineProperty(navigator, 'share', {value: (d) => { window.__shared = d; return Promise.resolve(); }, configurable: true}); Object.defineProperty(navigator, 'canShare', {value: () => true, configurable: true})")
    page.get_by_role('button', name='Share').click(); page.wait_for_timeout(300)
    shared = page.evaluate('window.__shared')
    assert shared['url'] == verify and 'Test Clinic' in shared['title']
    blob = ' '.join(str(v) for v in shared.values())
    for private in ('9876543210', '98765', 'priya@example.com'):
        assert private not in blob


def test_whatsapp_opens_prefilled_chat_only_on_click_and_never_includes_contact_details(browser_ctx):
    page, _e, card = open_card(browser_ctx)
    # (ends with `; 0` because Playwright would otherwise INVOKE the function this expression evaluates to)
    page.evaluate("window.__opened = []; window.open = (...a) => { window.__opened.push(a); return null; }; 0")
    page.wait_for_timeout(300)
    assert page.evaluate('window.__opened.length') == 0                    # nothing is sent or opened automatically
    page.get_by_role('button', name='WhatsApp').click()
    opened = page.evaluate('window.__opened')
    assert len(opened) == 1
    url = opened[0][0]
    assert url.startswith('https://wa.me/?text=') and 'noopener' in opened[0][2]
    from urllib.parse import unquote
    text = unquote(url.split('text=')[1])
    assert f'https://clinic.example/verify/{card.card_id}/' in text and 'Test Clinic' in text
    for private in ('9876543210', '98765', 'priya@example.com', 'Physiotherapist', card.holder.employee_id):
        assert private not in text


def test_print_view_shows_both_faces_and_hides_page_chrome(browser_ctx):
    page, _e, _c = open_card(browser_ctx)
    page.emulate_media(media='print')
    box = page.evaluate("(() => { const r = document.querySelector('.idc-offscreen').getBoundingClientRect(); return [r.left, r.top, r.width]; })()")
    assert box[0] >= 0 and box[2] >= 890                                    # off-screen faces are brought on-page for printing
    assert page.evaluate("getComputedStyle(document.querySelector('.idc-toolbar')).visibility") == 'hidden'


def test_back_face_lists_organisation_details_on_separate_lines(browser_ctx):
    page, _e, _c = open_card(browser_ctx)
    tops = page.evaluate("""[...document.querySelectorAll('[data-idc-export="back"] .idc-back-body p')]
                             .filter(p => /(\\d{8,}|@|https?:)/.test(p.textContent)).map(p => Math.round(p.getBoundingClientRect().top))""")
    assert len(tops) >= 3 and len(set(tops)) == len(tops)               # phone, email, website each on its own line


def test_arabic_date_is_not_split_by_the_latin_label(browser_ctx):
    page, _e, _c = open_card(browser_ctx, '?lang=ar')
    ok = page.evaluate("""(() => { const s = [...document.querySelectorAll('.idc-flip .idc-foot span')].find(x => x.querySelector('bdi'));
        return !!s && getComputedStyle(s.querySelector('bdi')).unicodeBidi === 'isolate'; })()""")
    assert ok
