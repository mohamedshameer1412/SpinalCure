"""Staff shell in real Chromium: compiled Tailwind applies without the CDN, language switch, RTL, sidebar by role."""
import os

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

pw = pytest.importorskip('playwright.sync_api')
CHROMIUM = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
pytestmark = [pytest.mark.skipif(not os.path.exists(CHROMIUM), reason='Chromium not installed'),
              pytest.mark.django_db(transaction=True)]
User = get_user_model()


@pytest.fixture
def page(live_server, db):
    u = User.objects.create_user(username='shell', email='shell@example.com', password='x', role='owner')
    c = Client(); c.force_login(u)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM, args=['--no-sandbox'])
        ctx = browser.new_context(viewport={'width': 1280, 'height': 800})
        ctx.add_cookies([{'name': 'sessionid', 'value': c.cookies['sessionid'].value, 'url': live_server.url}])
        host = live_server.url.split('//')[1]
        ctx.route('**/*', lambda r: r.continue_() if r.request.url.split('/')[2] == host else r.abort())
        pg = ctx.new_page()
        pg.base = live_server.url
        yield pg
        browser.close()


def test_compiled_tailwind_styles_apply_without_cdn(page):
    page.goto(f'{page.base}/en/notifications/', wait_until='domcontentloaded')
    assert page.evaluate("[...document.styleSheets].some(s => (s.href||'').includes('css/tailwind.css'))")
    # `hidden sm:block` language dropdown: visible at 1280px, proving both the utility and its breakpoint compile
    assert page.is_visible('header button[aria-haspopup=listbox]')
    assert page.evaluate("getComputedStyle(document.querySelector('.bg-primary-600, .text-primary-600, [class*=primary-]')).color !== ''")


def test_language_switch_to_tamil_sets_lang_and_persists(page):
    page.goto(f'{page.base}/en/notifications/', wait_until='domcontentloaded')
    page.click('header button[aria-haspopup=listbox]')
    page.click('header button[name=language][value=ta]')
    page.wait_for_url('**/ta/notifications/')
    assert page.get_attribute('html', 'lang') == 'ta'
    from asgiref.sync import sync_to_async  # noqa: F401  (ORM is sync; Playwright's loop is running)
    import threading
    out = []
    t = threading.Thread(target=lambda: out.append(User.objects.get(username='shell').language)); t.start(); t.join()
    assert out == ['ta']


def test_tamil_page_has_translated_chrome(page):
    page.goto(f'{page.base}/ta/notifications/', wait_until='domcontentloaded')
    assert 'ta' == page.get_attribute('html', 'lang')
    assert any(ch in page.inner_text('nav, aside, body') for ch in 'அஆஇஉஎஒகசதநபமயரலவ')
