"""Record the Spinal Cure walkthrough in a real browser, with captions and a visible cursor.

Frames come straight from Chrome's own screencast (Page.startScreencast), each with the exact time it was painted, so the
voice-over can be placed against the picture to the frame. (Playwright's built-in video lagged the clock by seconds on
heavy pages, which would put the voice ahead of the captions.)

    python demo/walkthrough/tts.py en          # voice-over clips first (their lengths set the pace)
    python demo/walkthrough/record.py en       # records out/en/frames/ + events.json
    python demo/walkthrough/postprocess.py en  # final MP4 with voice and subtitles

    DEMO_FAST=1 python demo/walkthrough/record.py en     # dry run: no pacing, no video; only proves every step works

Settings (environment): DEMO_BASE (default http://127.0.0.1:8003), CHROME_PATH, DEMO_EMAIL, DEMO_PASSWORD.
Run it against the disposable demo database only (see seed_demo.py): it creates one booking and edits nothing else.
"""
import base64
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

from narration import OUTRO, STEPS, TITLE

LANG = sys.argv[1] if len(sys.argv) > 1 else 'en'
ONLY = set(filter(None, os.environ.get('DEMO_ONLY', '').split(',')))      # e.g. DEMO_ONLY=intro,home to test a few steps
assert LANG in ('en', 'ta')
HERE = Path(__file__).resolve().parent
OUT = HERE / 'out' / LANG
FAST = os.environ.get('DEMO_FAST') == '1'
BASE = os.environ.get('DEMO_BASE', 'http://127.0.0.1:8003').rstrip('/')
CHROME = os.environ.get('CHROME_PATH', r'C:/Program Files/Google/Chrome/Application/chrome.exe')
EMAIL = os.environ.get('DEMO_EMAIL', 'demo.admin@spinalcure.local')
PASSWORD = os.environ.get('DEMO_PASSWORD', 'Demo@12345')
W, H = 1920, 1080
L = LANG
GUEST = {'en': ('Meera Krishnan', '9840099999', 'demo.meera@example.com'),
         'ta': ('Kavya Ramesh', '9840088888', 'demo.kavya@example.com')}[LANG]
OTHER = {'en': 'தமிழ்', 'ta': 'English'}[LANG]
HOME_LABEL = {'en': 'English', 'ta': 'தமிழ்'}[LANG]
IDX = 1 if LANG == 'en' else 2
TXT = 3 if LANG == 'en' else 4
STAGE = {s[0]: s[IDX] for s in STEPS}
TEXT = {s[0]: s[TXT] for s in STEPS}
DUR = json.loads((OUT / 'audio' / 'durations.json').read_text(encoding='utf-8')) if not FAST else {}

INIT_JS = r"""
(() => {
  const css = `
  #__cur{position:fixed;left:0;top:0;width:34px;height:34px;z-index:2147483647;pointer-events:none;transform:translate(-4px,-3px);
    filter:drop-shadow(0 2px 3px rgba(0,0,0,.45));transition:opacity .2s}
  .__rip{position:fixed;z-index:2147483646;pointer-events:none;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;
    border:3px solid #16a34a;background:rgba(22,163,74,.25);animation:__rip .55s ease-out forwards}
  @keyframes __rip{to{transform:scale(4.2);opacity:0}}
  #__cap{position:fixed;left:50%;bottom:34px;transform:translateX(-50%);max-width:1240px;width:max-content;z-index:2147483645;
    pointer-events:none;background:rgba(10,16,22,.86);color:#fff;border-radius:18px;padding:16px 30px 18px;opacity:0;
    transition:opacity .45s ease;font-family:'Segoe UI','Nirmala UI','Latha','Noto Sans Tamil',system-ui,sans-serif;text-align:center;
    box-shadow:0 10px 40px rgba(0,0,0,.35)}
  #__cap .s{font-size:15px;letter-spacing:.16em;text-transform:uppercase;color:#6ee7a8;font-weight:700;margin-bottom:6px}
  #__cap .t{font-size:27px;line-height:1.38;font-weight:500}`;
  const add = () => {
    if (document.getElementById('__cap')) return;
    const st = document.createElement('style'); st.textContent = css; document.documentElement.appendChild(st);
    const cur = document.createElement('div'); cur.id = '__cur';
    cur.innerHTML = '<svg viewBox="0 0 24 24" width="34" height="34"><path d="M4 2l15 9-6.5 1.6L9.5 19z" fill="#fff" stroke="#111" stroke-width="1.5" stroke-linejoin="round"/></svg>';
    document.documentElement.appendChild(cur);
    const cap = document.createElement('div'); cap.id = '__cap'; cap.innerHTML = '<div class="s"></div><div class="t"></div>';
    document.documentElement.appendChild(cap);
    let pos = [-60, -60]; try { pos = JSON.parse(sessionStorage.getItem('__cur') || 'null') || pos; } catch (e) {}
    cur.style.left = pos[0] + 'px'; cur.style.top = pos[1] + 'px';
    window.addEventListener('mousemove', e => { cur.style.left = e.clientX + 'px'; cur.style.top = e.clientY + 'px';
      try { sessionStorage.setItem('__cur', JSON.stringify([e.clientX, e.clientY])); } catch (x) {} }, true);
    window.addEventListener('mousedown', e => { const r = document.createElement('div'); r.className = '__rip';
      r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px'; document.documentElement.appendChild(r); setTimeout(() => r.remove(), 700); }, true);
    window.__cap = (stage, text) => {
      const s = cap.querySelector('.s'), t = cap.querySelector('.t');
      const apply = () => { s.textContent = stage; t.textContent = text; cap.style.opacity = '1'; };
      if (cap.style.opacity === '1') { cap.style.opacity = '0'; setTimeout(apply, 260); } else apply();
      try { localStorage.setItem('__cap', JSON.stringify([stage, text])); } catch (e) {}
    };
    window.__capHide = () => { cap.style.opacity = '0'; try { localStorage.removeItem('__cap'); } catch (e) {} };
    try { const saved = JSON.parse(localStorage.getItem('__cap') || 'null');
      if (saved) { cap.querySelector('.s').textContent = saved[0]; cap.querySelector('.t').textContent = saved[1]; cap.style.opacity = '1'; } } catch (e) {}
  };
  window.__demoAdd = add;
  if (document.documentElement) add(); else document.addEventListener('DOMContentLoaded', add);
  document.addEventListener('DOMContentLoaded', add);
})();
"""


def logo_url():
    html = urllib.request.urlopen(f'{BASE}/en/', timeout=20).read().decode('utf-8', 'replace')
    m = re.search(r'src="(/media/clinic/[^"]+\.png)"', html)
    return BASE + m.group(1) if m else ''


def card_html(logo, title, subtitle, bullets=(), note=''):
    items = ''.join(f'<li>{b}</li>' for b in bullets)
    return f"""<!doctype html><html lang="{L}"><head><meta charset="utf-8"><style>
    html,body{{margin:0;height:100%}}#__cur{{display:none!important}}
    body{{background:radial-gradient(1200px 700px at 20% 10%,#1a7a45 0%,#14532d 55%,#0b3d2e 100%);color:#fff;display:flex;align-items:center;
    justify-content:center;font-family:'Segoe UI','Nirmala UI','Latha',system-ui,sans-serif}}
    .box{{text-align:center;max-width:1300px;padding:0 60px 150px}}
    @keyframes glow{{0%,100%{{box-shadow:0 12px 40px rgba(0,0,0,.35)}}50%{{box-shadow:0 12px 56px rgba(110,231,168,.45)}}}}
    .logo{{animation:glow 3s ease-in-out infinite;width:150px;height:150px;border-radius:50%;background:#fff;padding:14px;box-sizing:border-box;object-fit:contain;
      box-shadow:0 12px 40px rgba(0,0,0,.35)}}
    h1{{font-size:88px;margin:28px 0 6px;font-weight:800;letter-spacing:.01em}}h2{{font-size:38px;margin:0 0 30px;font-weight:500;color:#d1fae5}}
    ul{{list-style:none;padding:0;margin:0 0 34px;font-size:26px;line-height:1.7;color:#ecfdf5}}li:before{{content:"✓  ";color:#6ee7a8}}
    .note{{display:inline-block;font-size:22px;padding:10px 24px;border:1px solid rgba(255,255,255,.35);border-radius:999px;color:#fde68a}}
    </style></head><body><div class="box">{f'<img class="logo" src="{logo}">' if logo else ''}<h1>{title}</h1><h2>{subtitle}</h2>
    <ul>{items}</ul>{f'<div class="note">{note}</div>' if note else ''}</div></body></html>"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    logo = logo_url()
    events, status = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True, args=['--force-device-scale-factor=1'])
        ctx = browser.new_context(viewport={'width': W, 'height': H}, locale='ta-IN' if L == 'ta' else 'en-IN')
        ctx.add_init_script(INIT_JS)
        clock0 = time.monotonic()
        page = ctx.new_page()
        page.set_default_timeout(25000)
        now = lambda: time.time()                                       # Chrome's frame clock is the same epoch time

        frames = []
        frame_dir = OUT / 'frames'
        cur = {'stage': '', 'text': ''}
        cdp_box = {}

        def CAPTURE_START():
            """Chrome's own screencast: every painted frame with its exact time (started once the first card is up)."""
            import shutil
            shutil.rmtree(frame_dir, ignore_errors=True)
            frame_dir.mkdir(parents=True)
            cdp = cdp_box['cdp'] = ctx.new_cdp_session(page)

            def on_frame(params):
                name = f'{len(frames):06d}.jpg'
                (frame_dir / name).write_bytes(base64.b64decode(params['data']))
                frames.append((params['metadata']['timestamp'], name))
                cdp.send('Page.screencastFrameAck', {'sessionId': params['sessionId']})

            cdp.on('Page.screencastFrame', on_frame)
            cdp.send('Page.startScreencast', {'format': 'jpeg', 'quality': 85, 'maxWidth': W, 'maxHeight': H, 'everyNthFrame': 1})

        # ── helpers ────────────────────────────────────────────────────────────────────────────
        def pause(s):
            page.wait_for_timeout(50 if FAST else int(s * 1000))      # keeps the screencast flowing (time.sleep would stall it)
            ensure_caption()

        def smooth_scroll(y, ms=1300):
            if FAST:
                page.evaluate('y => window.scrollTo(0, y)', y)
                return
            page.evaluate("""([y, ms]) => new Promise(res => { const y0 = window.scrollY, t0 = performance.now();
              const f = t => { const k = Math.min(1, (t - t0) / ms), e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
                window.scrollTo(0, y0 + (y - y0) * e); k < 1 ? requestAnimationFrame(f) : res(); }; requestAnimationFrame(f); })""", [y, ms])

        def scroll_to(sel, top=130, ms=1300):
            y = page.evaluate("([s, top]) => { const e = document.querySelector(s); return e ? e.getBoundingClientRect().top + window.scrollY - top : 0 }", [sel, top])
            smooth_scroll(max(0, y), ms)

        mouse = {'x': 960, 'y': 540}

        def move_to(x, y, ms=520):
            if FAST:
                page.mouse.move(x, y)
                mouse.update(x=x, y=y)
                return
            n = 26
            x0, y0 = mouse['x'], mouse['y']
            for i in range(1, n + 1):
                k = i / n
                e = k * k * (3 - 2 * k)
                page.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e)
                page.wait_for_timeout(ms / n)
            mouse.update(x=x, y=y)

        def target(loc):
            """Scroll the element into a comfortable spot (smoothly) and return its centre."""
            loc.first.wait_for(state='visible')
            box = loc.first.bounding_box()
            if box and (box['y'] < 110 or box['y'] + box['height'] > H - 230):
                page.evaluate("(b) => window.scrollBy(0, b)", box['y'] - 380)
                pause(0.8)
                box = loc.first.bounding_box()
            return box['x'] + box['width'] / 2, box['y'] + box['height'] / 2

        def hover(loc):
            move_to(*target(loc))

        def click(loc, after=0.6):
            x, y = target(loc)
            move_to(x, y)
            pause(0.3)
            page.mouse.down()
            pause(0.08)
            page.mouse.up()
            pause(after)

        def type_into(loc, text, delay=75):
            click(loc, after=0.15)
            page.keyboard.type(text, delay=0 if FAST else delay)

        def sidebar(path):
            """Click a staff sidebar link by its address, scrolling the sidebar if needed."""
            link = page.locator(f'aside a[href="/{L}{path}"]').first
            link.scroll_into_view_if_needed()
            click(link, after=0.4)
            page.wait_for_load_state('domcontentloaded')
            page.wait_for_timeout(300 if FAST else 900)

        def goto(path):
            page.goto(f'{BASE}/{L}{path}', wait_until='domcontentloaded')
            page.wait_for_timeout(300 if FAST else 900)

        # ── steps ──────────────────────────────────────────────────────────────────────────────
        def s_intro():
            t, sub, bullets, note = TITLE[L]
            show_card_page(card_html(logo, t, sub, bullets, note))
            pause(0.2)

        def p_home():
            goto('/')
            page.locator('h1').first.wait_for()

        def s_home():
            pause(0.5)
            pause(1.5)
            hover(page.locator(f'header a[href="/{L}/#book"]').first)

        def s_about():
            smooth_scroll(0, 400)
            scroll_to('#about', top=140)
            pause(1.0)

        def s_treatments():
            scroll_to('#treatments', top=120)
            pause(2.0)
            smooth_scroll(page.evaluate('window.scrollY') + 360, 1600)

        def s_doctor():
            scroll_to('#doctor', top=120)

        def p_stories():
            click(page.locator(f'header a[href="/{L}/clinic/testimonials/"]').first)
            page.wait_for_url(re.compile(r'/clinic/testimonials/'))
            page.wait_for_selector('article')

        def s_stories():
            pause(1.0)
            smooth_scroll(420, 1300)
            pause(1.5)
            before = page.locator('article').count()
            more = page.locator('a[href*="vl="]').first
            click(more, after=0.2)
            page.wait_for_function('n => document.querySelectorAll("article").length > n', arg=before)
            pause(1.2)

        def p_book_details():
            goto('/')
            click(page.locator(f'header a[href="/{L}/#book"]').first, after=0.3)
            page.wait_for_selector('#bk-name')
            scroll_to('#book', top=100, ms=1000)

        def s_book_details():
            type_into(page.locator('#bk-name'), GUEST[0])
            type_into(page.locator('#bk-phone'), GUEST[1])
            type_into(page.locator('#bk-email'), GUEST[2], delay=55)

        def s_book_date():
            click(page.locator('#book input.flatpickr-alt').first, after=0.5)
            cal = page.locator('.flatpickr-calendar.open')
            cal.wait_for()
            idx = page.evaluate("""() => { const t = new Date(); t.setHours(0,0,0,0);
              const d = [...document.querySelectorAll('.flatpickr-calendar.open .flatpickr-day')];
              return d.findIndex(e => e.dateObj && e.dateObj > t && e.dateObj.getDay() === 2 && !e.className.includes('disabled')
                                      && !e.className.includes('Month')); }""")
            assert idx >= 0, 'no open Tuesday in the calendar'
            click(page.locator('.flatpickr-calendar.open .flatpickr-day').nth(idx), after=0.4)
            page.wait_for_selector('#book [role=radio]')
            pause(1.6)

        def s_book_confirm():
            slots = page.locator('#book [role=radio]')
            click(slots.nth(min(3, slots.count() - 1)), after=0.5)
            type_into(page.locator('#bk-notes'), 'Lower back pain' if L == 'en' else 'முதுகுவலி', delay=60)
            click(page.locator('#book form button[type=submit]').first, after=0.2)
            page.wait_for_selector('#book form button[type=submit]', state='hidden', timeout=45000)
            pause(1.0)

        def p_language():
            goto('/')

        def s_language():
            other_code = 'ta' if L == 'en' else 'en'
            click(page.locator('header button:visible', has_text=HOME_LABEL).first, after=0.8)
            click(page.locator('header button:visible', has_text=OTHER).first, after=0.2)
            page.wait_for_url(re.compile(f'/{other_code}/'))
            page.wait_for_load_state('domcontentloaded')
            page.wait_for_timeout(300 if FAST else 2500)
            # and back to the language of this video
            click(page.locator('header button:visible', has_text=OTHER).first, after=0.8)
            click(page.locator('header button:visible', has_text=HOME_LABEL).first, after=0.2)
            page.wait_for_url(re.compile(f'/{L}/'))
            page.wait_for_load_state('domcontentloaded')
            page.wait_for_timeout(300 if FAST else 1500)

        def p_faq():
            goto('/clinic/faq/')

        def s_faq():
            first = page.locator('details summary, button[aria-expanded]').first
            click(first, after=0.8)
            smooth_scroll(260, 1000)

        def p_login():
            goto('/accounts/login/')

        def s_login():
            type_into(page.locator('input[type=email], input[name=username]').first, EMAIL, delay=55)
            type_into(page.locator('input[type=password]').first, PASSWORD, delay=70)
            click(page.locator('button[type=submit]').first, after=0.2)
            page.wait_for_url(re.compile(r'/analytics/dashboard/'))

        def s_dashboard():
            pause(1.5)
            smooth_scroll(500, 1800)
            pause(1.0)
            smooth_scroll(0, 1200)

        def p_appointments():
            sidebar('/appointments/')
            page.wait_for_timeout(300 if FAST else 2500)

        def s_appointments():
            click(page.locator(f'a[href="/{L}/appointments/list/"]').first, after=0.3)
            page.wait_for_url(re.compile(r'/appointments/list/'))
            page.wait_for_selector('table tbody tr')
            pause(1.0)
            hover(page.locator('table tbody tr', has_text=GUEST[0].split()[0]).first)

        def p_availability():
            sidebar('/appointments/availability/')
            page.wait_for_selector('select[name=d0_m_start]', state='attached')

        def s_availability():
            pause(2.0)
            smooth_scroll(260, 1200)

        def p_patients():
            sidebar('/patients/')
            page.wait_for_selector('table tbody tr')

        def s_patients():
            type_into(page.locator('#table-search'), 'Priya', delay=110)
            page.wait_for_function('() => document.querySelectorAll("table tbody tr").length <= 2')
            pause(1.0)

        def p_patient_detail():
            click(page.locator('table tbody tr a[href*="/patients/"]').first, after=0.4)
            page.wait_for_url(re.compile(r'/patients/[A-Za-z0-9_-]{22}/'))

        def s_patient_detail():
            pause(1.5)
            smooth_scroll(520, 1800)
            pause(1.0)
            smooth_scroll(0, 1200)

        def p_payments():
            sidebar('/payments/')
            page.wait_for_selector('table tbody tr')

        def s_payments():
            hover(page.locator('table tbody tr').nth(1))
            pause(1.5)

        def p_report():
            sidebar('/payments/report/')

        def s_report():
            pause(2.5)

        def p_courses():
            sidebar('/courses/')
            page.wait_for_selector('a[href$="/batches/"]')

        def s_courses():
            click(page.locator('a[href$="/batches/"]').first, after=0.4)
            page.wait_for_url(re.compile(r'/batches/$'))
            page.locator('a.absolute.inset-0').first.wait_for(state='attached')
            hover(page.locator('h3').first)
            pause(1.0)
            click(page.locator('h3').first, after=0.3)       # the whole card opens the batch
            page.wait_for_url(re.compile(r'/registrations/'))
            pause(1.5)

        def p_attendance():
            click(page.locator('a[href*="/attendance/"]').first, after=0.3)
            page.wait_for_url(re.compile(r'/attendance/'))
            page.wait_for_selector('table input[type=checkbox]')

        def s_attendance():
            pause(2.5)
            smooth_scroll(200, 1000)

        def p_students():
            sidebar('/courses/students/')
            page.wait_for_selector('table tbody tr')

        def s_students():
            pause(2.0)

        def p_student_detail():
            click(page.locator('table tbody tr a', has_text='Anitha').first, after=0.4)
            page.wait_for_url(re.compile(r'/courses/students/'))
            page.wait_for_selector('img[src*="/card/front.png"]')

        def s_student_detail():
            pause(1.2)
            smooth_scroll(380, 1500)
            pause(2.0)

        def p_idcards():
            sidebar('/idcards/')

        def s_idcards():
            pause(1.5)
            href = page.evaluate("""(l) => { const re = new RegExp('^/' + l + '/idcards/[0-9a-f-]{36}/$');
              const a = [...document.querySelectorAll('main a[href]')].find(e => re.test(e.getAttribute('href'))); return a && a.getAttribute('href'); }""", L)
            assert href, 'no ID card detail link on the page'
            click(page.locator(f'a[href="{href}"]').first, after=0.4)
            page.wait_for_selector('.idc-stage')
            pause(2.0)
            smooth_scroll(120, 900)

        def p_videos():
            sidebar('/clinic/admin/videos/')
            page.wait_for_selector('main')

        def s_videos():
            pause(1.5)
            smooth_scroll(560, 1800)

        def p_setup():
            sidebar('/clinic/admin/setup/')

        def s_setup():
            pause(2.0)
            smooth_scroll(700, 2000)

        def s_outro():
            title, line = OUTRO[L]
            show_card_page(card_html(logo, title, line))
            pause(0.2)

        PRE = {k[2:]: v for k, v in list(locals().items()) if k.startswith('p_') and callable(v)}

        ACTIONS = {
            'intro': s_intro, 'home': s_home, 'about': s_about, 'treatments': s_treatments, 'doctor': s_doctor,
            'stories': s_stories, 'book_details': s_book_details, 'book_date': s_book_date, 'book_confirm': s_book_confirm,
            'language': s_language, 'faq': s_faq, 'login': s_login, 'dashboard': s_dashboard, 'appointments': s_appointments,
            'availability': s_availability, 'patients': s_patients, 'patient_detail': s_patient_detail, 'payments': s_payments,
            'report': s_report, 'courses': s_courses, 'attendance': s_attendance, 'students': s_students,
            'student_detail': s_student_detail, 'idcards': s_idcards, 'videos': s_videos, 'setup': s_setup, 'outro': s_outro,
        }

        def show_card_page(html):
            page.set_content(html)
            page.evaluate('window.__demoAdd && window.__demoAdd()')

        def ensure_caption():
            if FAST or not cur['text']:
                return
            try:
                page.evaluate("""([s, t]) => { const c = document.getElementById('__cap');
                  if (!c || c.querySelector('.t').textContent !== t) window.__cap && window.__cap(s, t); }""", [cur['stage'], cur['text']])
            except Exception:                                         # a navigation was in flight; the next pause retries
                pass

        trim = 0.0
        for sid, *_ in STEPS:
            if ONLY and sid not in ONLY:
                continue
            if sid == 'intro':
                page.goto(f'{BASE}/robots.txt')                        # a real page first: the card then renders at the full 1920x1080
                show_card_page(card_html(logo, *TITLE[L]))
                page.wait_for_timeout(600)
                if not FAST:
                    CAPTURE_START()
                page.wait_for_timeout(500)
                trim = now()                                           # everything before this (blank first frame) is cut
            err = ''
            if sid in PRE:
                try:
                    cur.update(stage='', text='')
                    page.evaluate('window.__capHide && window.__capHide()')
                    PRE[sid]()
                except Exception as exc:                               # noqa: BLE001
                    err = f'{type(exc).__name__}: {(str(exc).splitlines() or [''])[0][:200]}'
                    try:
                        page.screenshot(path=str(OUT / f'fail_{sid}_pre.png'))
                    except Exception:
                        pass
            cur.update(stage=STAGE[sid], text=TEXT[sid])
            for attempt in range(8):                                   # a navigation may still be settling
                try:
                    start = page.evaluate('([s, t]) => { window.__cap && window.__cap(s, t); return Date.now() / 1000 }', [STAGE[sid], TEXT[sid]])
                    break
                except Exception:
                    page.wait_for_timeout(400)
            else:
                raise RuntimeError('could not set the caption')
            try:
                if sid != 'intro' and not err:
                    ACTIONS[sid]()
            except Exception as exc:                                     # noqa: BLE001 - record and carry on
                err = f'{type(exc).__name__}: {(str(exc).splitlines() or [''])[0][:200]}'
                try:
                    page.screenshot(path=str(OUT / f'fail_{sid}.png'))
                except Exception:
                    pass
            if not FAST:
                wait = start + DUR[sid] + 0.8 - now()
                if wait > 0:
                    page.wait_for_timeout(int(wait * 1000))
            end = now()
            events.append({'id': sid, 'start': start, 'end': end, 'text': TEXT[sid], 'stage': STAGE[sid]})
            status.append({'id': sid, 'ok': not err, 'error': err, 'seconds': round(end - start, 1)})
            print(f"{'PASS' if not err else 'FAIL'}  {sid:15s} {end - start:5.1f}s  {err}", flush=True)

        page.evaluate('window.__capHide && window.__capHide()')
        page.wait_for_timeout(700)
        total = now()
        if not FAST:
            cdp_box['cdp'].send('Page.stopScreencast')
        ctx.close()
        browser.close()
    (OUT / 'events.json').write_text(json.dumps({'trim': trim, 'total': total, 'events': events, 'status': status},
                                                ensure_ascii=False, indent=1), encoding='utf-8')
    if not FAST:
        (OUT / 'frames.json').write_text(json.dumps(frames), encoding='utf-8')
    failed = [s for s in status if not s['ok']]
    print(f"{len(status) - len(failed)}/{len(status)} steps passed; recorded {total - trim:.0f}s, {len(frames)} frames")
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
