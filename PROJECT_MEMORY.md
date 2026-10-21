# Spinal Cure: project memory

Everything known about this project from the build sessions (October 2026): setup, decisions, data sources, what was built, what was fixed, and what is still open. Read this first when picking the work up again.

Last updated: 2026-10-20. Branch `main`, last commit `affbff1`. **All work below is uncommitted** (about 180 changed or new files).

---

## 1. The clinic

| | |
|---|---|
| Name | Spinal Cure, "Neck & Back Pain Special Care Center" |
| Tagline | Advanced Holistic Spine & Pain Care |
| Doctor | Dr. R. Basheer Basha (signs as "Acu. Healer"), Specialist in Classical Acupuncture Science |
| Qualifications (from the signboard) | B.Sc., Master Diploma (Acu), Master Diploma in Classical (Acu), Doctor of Medicine in (Acu), Colombo University, Sri Lanka. General Secretary, CASMA (Classical Acupuncture Science Medical Association) |
| Address (Google, current) | No: 194/4, 1st Floor, JN Salai, 100ft Main Rd, near Aladipattiyaan Karupatti Coffee, Sri Sakthi Nagar, Arumbakkam, Chennai, Tamil Nadu 600106 |
| Older address (YouTube descriptions) | Old No 424, New No 797, P.H. Road, Arumbakkam (near DG Vaishnav College), Chennai 600106. **Not used.** |
| Phones | +91 81480 38363, +91 90876 28476 |
| Email | spinalcure2015@gmail.com |
| Hours (Google) | Mon, Tue, Wed, Thu, Sat 5:30–8:30 pm; Fri 10 am–1 pm; Sun closed |
| Hours (YouTube, longer, possibly outdated) | Mon–Sat 9:30–1:30 and 5:30–9 pm; Fri 10–12:30 and 5:30–9 pm; Sun closed. **Not used.** |
| Google rating | 5.0 from 113 reviews |
| Google Maps place | `0x3a5267aee2e99775:0x762300885f10b7d6`, lat 13.0676457, lng 80.2089538 |
| Instagram | https://www.instagram.com/spinalcure_chennai/ (about 811 followers, 358 posts; highlights: Testimonials, Neck pain, Back pain, Disc Problem, Spine Care, Sciatica) |
| YouTube | https://www.youtube.com/@SpinalCure ("Spinal Cure Chennai", 193 videos, 161 Shorts) |
| Old website | spinalcure.in does not resolve (dead domain) |
| Clinic promise | "No Surgery, No Medicine, No Diet" (on the signboard). ID card back says "Without Surgery, Without Medicine and Without Diet". |
| Conditions on the signboard | Headache, migraine, insomnia and depression, asthma and sinuses, tonsillitis; cervical neck pain, C1–C8 disc issues, stiff neck and spondylitis, shoulder pain, thyroid and vertigo; L1–L5 disc bulge, herniated disc, sciatica and disc prolapse, knee, leg and heel pain; menstrual disorders and PCOD, impotence and infertility, rheumatoid arthritis and paralysis, neurology issues, varicose veins; hair fall, skin allergy, acidity and gastro, piles, gallbladder stone |
| Academy | Runs classical acupuncture courses (YouTube: "Batch 1 classical Acupuncture students", "Healing Hands Certified") |

---

## 2. Tech stack and environment

- **Django** (installed version is newer than the `Django==4.2.*` pin in `requirements.txt`; the code runs on Django 6.x behaviour). DRF, simplejwt, drf-spectacular, django-ratelimit, django-tailwind.
- **Database: MariaDB** (`DB_ENGINE` defaults to mysql), database `spinalcure_db`, user root. Credentials are in `.env`.
- **Frontend:** server-rendered Django templates + Tailwind CSS 3 (compiled, committed) + Alpine.js + htmx + Tom Select + Chart.js + Bootstrap Icons. Everything is vendored in `static/vendor` (no CDN), except Razorpay's `checkout.js` on the payment page.
- **Fonts:** self-hosted Noto for Tamil, Devanagari, Telugu, Malayalam and Kannada, plus Inter and Outfit (`static/fonts`, `static/css/fonts.css`). The ID-card renderer uses TTFs from the same folder; the Telugu, Malayalam and Kannada TTFs were converted from fontsource WOFF2 (script-only subsets).
- **OS:** Windows, Git Bash plus PowerShell. Python 3.13 (user site-packages).

### Environment quirks (these will bite)

1. **`DJANGO_ENV` defaults to `production`**, which refuses to start without `FERNET_KEYS`. Locally always run `DJANGO_ENV=development python manage.py ...`. Tests use `DJANGO_SETTINGS_MODULE=spinalcure.settings.test`.
2. **Legacy UUID columns.** Existing tables store UUID primary keys as `char(32)`, but new tables get MariaDB's native `uuid` type. **A foreign key from a new table to an old table fails** (`errno 150`). Work-arounds used:
   - `TestimonialVideo` has no `clinic` FK (single clinic).
   - `Translation` stores `model_label` + `object_id` as text.
   - `OnlineOrder` stores `payment_ref` as text instead of an FK to `Payment`.
   - Avoid FKs from new models to old tables, or use `db_constraint=False` with care.
3. **Patient `name` is encrypted** (`EncryptedCharField`): it cannot be filtered in SQL. Filter in Python.
4. **Windows console is cp1252.** Use `PYTHONUTF8=1` (or `PYTHONIOENCODING=utf-8`) when printing Tamil or Telugu text, otherwise you get UnicodeEncodeError or mojibake ("Booking…" prints as "Booking�").
5. **Bash heredocs that contain `\\` or nested quotes break.** Write a temporary `.py` file with the Write tool instead.
6. **Pillow has no libraqm here**, so complex scripts are not shaped in server-rendered ID-card PNGs. `idcards/render.py` falls back to basic layout (`_dir()`); production should install libraqm (see DEPLOY.md).
7. **Tailwind build:** `cd theme/static_src && npm run build`. The build deletes `static/css/tailwind.css` first, so a failed build leaves no CSS. Escape `/` in selectors inside `tailwind.config.js` as `\\/`.
8. **Browsers cache `tailwind.css` hard** (same URL every build). After rebuilding, force-refresh, or fetch with `{cache:'reload'}` in Playwright.
9. **The dev server runs with `--noreload`** in these sessions: restart it after changing URLs or Python code.
10. **Missing locally:** `polib` was pip-installed during the session (needed by the i18n tests and scripts).

### Demo logins (dev database only, created by `scripts/seed_demo_users.py`)

| Role | Username | Email | Password |
|---|---|---|---|
| Super Admin | admin | admin@spinalcure.local | Admin@12345 |
| Clinic Admin | clinicadmin | clinicadmin@spinalcure.local | Clinic@12345 |
| Owner | owner | owner@spinalcure.local | Owner@12345 |
| Doctor | doctor | doctor@spinalcure.local | Doctor@12345 |
| Receptionist | reception | reception@spinalcure.local | Recept@12345 |
| Staff | staff1 | staff1@spinalcure.local | Staff@12345 |

Login page: `/en/accounts/login/` (login is by email). The seed script refuses to run with `DJANGO_ENV=production`.

---

## 3. Commands

```bash
# local server
DJANGO_ENV=development python manage.py runserver 127.0.0.1:8001 --noreload

# seed (dev only, idempotent)
python scripts/seed_demo_users.py          # the six demo logins
PYTHONUTF8=1 python scripts/seed_real_data.py   # real clinic content; deletes known dummy rows

# tests (browser tests need Linux Chromium and are skipped on Windows)
DJANGO_SETTINGS_MODULE=spinalcure.settings.test python -m pytest --maxfail=1000 --ignore=tests/browser --ignore=tests/integration/test_migrations.py -q -p no:cacheprovider

# css
cd theme/static_src && npm run build

# translations (UI strings)
python scripts/i18n_extract.py                   # refresh locale/*/django.po from code
PYTHONUTF8=1 python scripts/i18n_batch.py list 200 0 > tmp/i18n_todo.jsonl   # [msgid, plural, [langs needed]]
python scripts/i18n_batch.py apply batch.json    # {"msgid": {"ta": "...", "te": ["sing", "plural"]}}
python scripts/i18n_compile.py                   # rebuild .mo
```

A database backup taken before the dummy-data cleanup is in `tmp/backup_2026-10-19/` (`dumpdata` per app; `tmp/` is gitignored). It contains patient data: keep it private.

---

## 4. Languages

- **Site languages, in menu order:** English (`en`), Tamil (`ta`), Hindi (`hi`), Telugu (`te`), Malayalam (`ml`), Kannada (`kn`). **Arabic was removed** from `LANGUAGES` (its catalogue stays in `locale/ar`). RTL code paths still exist but are unused.
- Model language choices come from `spinalcure/languages.py` (`NATIVE_CHOICES`, native names via Django's `get_language_info`).
- **Two translation systems:**
  1. **UI strings** (`{% translate %}`, `gettext`): `locale/<lang>/LC_MESSAGES/django.po`. Drafted by AI, flagged for native-speaker review.
  2. **Website content** (clinic profile, services, doctor, testimonials, problems, videos, blog, events, courses): DB table `clinic.Translation`, managed in **Admin → Translations** and in the **translation panel under every content form**. Code: `clinic/content_i18n.py` (registry, statuses, providers), `clinic/translation_views.py`, `clinic/templatetags/content_i18n.py` (filters `tx`, `tx_html` (sanitised), `lines`; tag `translation_panel`).
- **Content translation rules** (copied from the Swagatam invitation builder, `D:\projects\Deep Aspects\Invitation\swagatam\src\engine\i18n\units.ts`): statuses missing, auto, edited, final, plus "stale" when the English source hash changed. A machine never overwrites edited or final text, except through "Regenerate".
- **Providers** (picked from env): `ANTHROPIC_API_KEY` (Claude, default model `claude-haiku-5-5`, transliterates names) → `GOOGLE_TRANSLATE_API_KEY` → free MyMemory (about 5,000 characters a day; **quota already exhausted on 2026-10-20**). Auto-translate now stops at the first quota error with one message.
- **Layout robustness:** `styles.css` scales `.display` and `.h-section` down for non-English, raises line height and removes letter-spacing (`html:not([lang='en'])`). The public nav collapses into a drawer below `xl`, and buttons use `whitespace-nowrap`.

### Translation status (IN PROGRESS)

UI catalogue after the rebuild: 2,175 strings.

| Language | Untranslated |
|---|---|
| ta, hi | 303 each (strings added during the rebuild) |
| te, ml, kn | 2,175 each (new catalogues) |

The to-do list is exported to `tmp/i18n_todo.jsonl` (303 strings need all five languages, 1,872 need te/ml/kn only). The plan was to write the translations in batches and apply them with `i18n_batch.py apply`, then `i18n_compile.py`. `tests/integration/test_i18n.py::test_catalogue_is_complete...` fails until this is done.

**Content translations** (DB) are also mostly empty for every language: fill them through Admin → Translations once a Claude or Google key is set, or write them by hand.

---

## 5. What was built (feature map)

### Data model additions
- `clinic.ProblemCategory` (name, slug, keywords, order): drives the problem filter.
- `clinic.ClinicTestimonial`: added `problem`, `owner_reply`, `source_url`, `posted_label`.
- `clinic.TestimonialVideo`: YouTube Short/video or Instagram reel URL; parsed to `platform` and `video_id`; `embed_url`, `thumbnail_url`, `is_vertical`.
- `clinic.Translation`: content translations (see section 4).
- `accounts.StaffProfile`: added `gender`, `date_of_birth`, `address`, and `blood_group` choices. Collected in Admin → Team Accounts → Edit User → "Personal details" (with photo upload).
- `idcards.IDCard.show_blood_group` now defaults to True.
- `payments.OnlineOrder` (Razorpay) and payment mode `razorpay`.
- Private uploads (`users/`, `patients/`, `expenses/`) now get random file names (`spinalcure/uploads.py::RandomName`).

### Public site (all pages extend `templates/public_base.html`)
- Shared header (`templates/public/header.html`): utility bar, logo, nav, language menu, "Book appointment", mobile drawer. Shared footer (`templates/public/footer.html`).
- **Home** `clinic/home.html` (view `clinic_portfolio_view`, URL `/<lang>/clinic/portfolio/`). Sections: hero, promise, treatments with problem chips, doctor, how it works, stories (videos and reviews), courses and events, visit and book. The booking form partial `clinic/partials/booking_form.html` uses `appointments/api/available-slots/` and `clinic/ajax/book-appointment/` (JSON, honeypot `website`, `request_key`).
- **Patient stories** `clinic/testimonials_public.html`: htmx search by keyword, problem and type; video modal (iframe created on click only); "Show more" paging; **public review form** (stores an unpublished ClinicTestimonial).
- Doctor profile, About, Blog list and detail, Course detail (registration), Events list and detail, registration manage pages, patient portal (login, verify, dashboard), appointment manage, online payment page.
- Old `portfolio_spa.html` and `portfolio.html` were deleted.
- Logo: `media/clinic/spinal_cure_logo.png` (transparent), `_on_dark.png` (white lettering, used in the footer and dark panels), `_white.png` (original). The context processor exposes `clinic_logo_dark_url`.

### Staff app ("UI kit")
- Theme tokens in `theme/static_src/tailwind.config.js`: every gray, slate, green, red… utility maps to CSS variables; `html.dark` mirrors the tints (50–300) and lightens text shades. Light, dark and system modes; the toggle is in the top bar (`Alpine.store('theme')`).
- Components in `theme/static_src/src/styles.css`: `.btn*`, `.card*`, `.badge*`, `.alert*`, `.ui-table`, `.menu*`, `.dialog*`, `.tabs`, `.dropzone`, `.toast`, `.nav-item`, `.stat`, public `.display`, `.h-section`, `.container-site`, and others.
- Behaviour in `static/js/ui.js`: theme store, toast store, automatic drag-and-drop dropzone for every `input[type=file]`. Public pages have `data-fixed-theme` and stay light.
- Shell: `templates/base.html` + `templates/ui/{sidebar,topbar,nav_item,command_search}.html`. Sidebar groups: Overview, Clinical, Financials, Education, Content & Reputation, Workspace, Administration; "Public Site" is pinned at the bottom.
- Reference page `/<lang>/ui-kit/` (staff only).
- Dashboard KPI cards rebuilt. 113 ad-hoc white panels converted to `.card`. Inline flash messages removed (they show as toasts now).
- Admin pages added: Reels & Shorts, Problem Categories, Translations, and a translation panel on clinic setup, specialists, testimonials, blog, events, courses and batches.

### ID card (vertical 560×900)
- **Front:** photo, name, role, ID and type pill, gender, date of birth, blood group, phone, home address, verify QR, status.
- **Back:** yin-yang emblem, the promise, clinic address, phones, email, website QR, card ID and validity, legal footer.
- Two renderers must agree: HTML/CSS (`idcards/templates/idcards/_face.html`, `static/css/idcard.css`) and Pillow (`idcards/render.py`).

### Emails
- One layout, `templates/emails/base_email.html` (table-based, logo, contact strip, footer), with brand data from `{% email_brand %}` in `clinic/templatetags/email_tags.py` (absolute URLs from `SITE_URL`).
- `notifications/email.html` (all automated notifications) and `payments/emails/receipt_email.html` extend it.

### Razorpay
- Code: `payments/razorpay.py` (stdlib HTTPS, HMAC checks), `payments/online.py`, `payments/online_views.py`.
- Flow: the invoice page has "Create payment link" for the balance (`billing.manage`) → public `/<lang>/payments/pay/<token>/` → Checkout → `pay/<token>/verify/` (signature) → `mark_paid` (idempotent, emails the receipt). Webhook: `/payments/razorpay/webhook/` (HMAC, `payment.captured` / `order.paid`).
- Tests: `tests/unit/test_razorpay.py`.

**What is needed from you for Razorpay:**
1. A Razorpay account with KYC (PAN, business proof, bank account for settlements).
2. API keys (test first, then live): `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`.
3. A webhook in the Razorpay dashboard pointing to `https://<domain>/payments/razorpay/webhook/` with events `payment.captured` and `order.paid`, plus its secret in `RAZORPAY_WEBHOOK_SECRET`.
4. `SITE_URL` set to the live https domain.
5. Decide the scope: today it covers a payment's balance. Online payment at course/event registration or booking time is not built.

### Real data import
- `scripts/seed_real_data.py`: deletes known dummy rows (sample testimonials, videos, blog posts, expenses, notifications, the two fake specialists, "Test …" patients, two fake reviews, the "camp" and "Test Event Script" events), then loads real content: clinic profile, signboard services, the doctor, problem categories, Google reviews and YouTube/Instagram videos. Data files are `scripts/data/google_reviews.json` and `scripts/data/youtube_shorts.json`.
- **Limits:** Google shows only 3 reviews without sign-in (the full text and owner replies are stored). Instagram allowed 12 reels without login (no captions). The doctor photo `media/practitioners/basheer_basha.jpg` is cropped from YouTube video `MT7Jo-HKU6U` (stern expression) and **should be replaced** with a proper portrait.
- Patients still in the dev DB that may be dummy (ask before deleting): Mohamed Shameer, Kavitha, Anjali Krishna, Venkatesh Prasad, Murugan Pillai, Deepa Iyer. The course "Basic Acupuncture Certification" and batch "Winter Intake 2025" also look like sample data.

---

## 6. Security work (guidance-mode audit, 2026-10-20)

Fixed (with tests where noted):

| Severity | Issue | Fix |
|---|---|---|
| High | Stored XSS between staff: the acupuncture case sheet rendered with `|safe` inside Alpine `x-data` | Render via `json_script`; save path accepts only a JSON object (`tests/integration/test_xss_regressions.py`) |
| High (data integrity) | Public review form created or attached reviews to **patient records** by phone number, with no rate limit | Stores an unpublished `ClinicTestimonial`; 5/h per IP; honeypot |
| Medium | `/accounts/settings/` let any user set their email to another user's (login is by email, so the admin could be locked out) | `ProfileForm` with case-insensitive unique email (test in `test_staff_role_sweep.py`) |
| Medium | Staff login had no brute-force limit | 10/min per IP, 20/h per account name (`accounts/urls.py`) |
| Low | Private uploads kept original names under public `/media/` | Random names for new uploads |
| Bug | `EncryptedJSONField` crashed on save (case sheets could never be saved) | Fixed in `spinalcure/fields.py` |
| Bug | Invoice view returned 500 on an unknown id | Now 404 |
| Bug | Global search crashed on guest bookings | Fixed |
| Bug | Invoice email returned the raw exception text | Generic message |
| Bug | Translation quota errors repeated for every batch | Stops at the first quota error |
| Note | Old translation-action `next` redirect | Validated with `url_has_allowed_host_and_scheme` |

Open security items (needs validation or a decision):
- Existing private files under `media/patients`, `media/users` and `media/expenses` keep their old guessable names. Rename them, or serve `/media/` privately (the web server config isn't in the repo).
- Rate limits use `REMOTE_ADDR`. Behind a proxy every visitor shares one IP: configure the real-IP header in the proxy/WSGI layer.
- Razorpay `checkout.js` loads without SRI (Razorpay changes the file in place; SRI would break checkout).
- Patient portal logout is a GET link (low).
- `map_iframe_url` is rendered `|safe` (admin-only input, by design).
- `/security-review` could not run (no `origin/HEAD` remote). The pending changes were reviewed manually.

---

## 7. Over-engineering audit (`/ponytail-audit`), 2026-10-20

Applied:
- Deleted 6 unused templates, `scripts/i18n_wrap*.py`, and scratch files.
- Removed unused dependencies (`python-docx`, `django-anymail`, `factory-boy`, `faker`, `pytest-xdist`) and `django-compressor` (app, settings, finder).

Not applied (needs your call):
- Delete the 6 root status docs (`ENTERPRISE_SUMMARY`, `PROJECT_STATUS`, `TEST_SUITE_SUMMARY`, `TESTING_GUIDE`, `API_DOCUMENTATION`, `I18N_SETUP_GUIDE`, about 2,800 lines); they are stale against the code.
- Replace `templates/components/alpine_select.html` (140 lines) with a native `<select>`, which Tom Select already enhances. Used in the calendar booking modal and patient detail.

---

## 8. Open work (priority order)

1. **Finish UI translations** for ta, hi, te, ml, kn (section 4), then `i18n_compile.py` and the i18n tests.
2. **Content translations** for all five languages (needs a Claude or Google key, or manual entry).
3. Replace the doctor photo. Confirm or delete the remaining possibly-dummy patients, course and batch.
4. Polish the remaining public screens visually: event detail, the registration manage pages, ID card verify/share pages, and the portal dashboard internals.
5. Check every staff page in light and dark mode (only the main ones were screenshot-checked). Run the browser tests on Linux.
6. Razorpay go-live (section 5). Optionally add online payment at course/event registration.
7. Production: set `SITE_URL`, `FERNET_KEYS`, `SECRET_KEY`, `ALLOWED_HOSTS`, the translation key, the Razorpay keys, install libraqm, configure the proxy real-IP header, and decide on `/media/` privacy.
8. Commit the work (nothing from these sessions is committed yet).

## 9. User preferences seen

- Wants enterprise-level, professional UI. Rejected the earlier look as "sucks"; cares about long Indic text not breaking layouts.
- Wants real data scraped from Google, YouTube and Instagram rather than dummy data.
- Prefers that I ask when unsure, but accepts sensible defaults. Chose "everything in one pass" for the UI rebuild.
- Uses the ponytail (lazy, minimal) style and asked for the security, ponytail and replica skills.
- Languages: English, Tamil, Hindi, Telugu, Malayalam, Kannada. No Arabic.

---

## Session 2026-10-20/21 additions

- **No browser-default UI** (standing rule): every `<select>` is a Tom Select and every date/time input a flatpickr calendar, both wired globally in `static/js/ui.js` (MutationObserver picks up Alpine/htmx content; opt out only with `data-native`). Native `confirm()`/`alert()` replaced by the kit dialog (`data-confirm`) and toasts. Phone fields use `.input-group` with a +91 addon (`window.withCountryCode`).
- **Patient stories**: every card is a designed cover (no patient faces on listings); 4 designs × per-problem colours, position-based so neighbours differ (`stories.with_slots`). Staff-uploaded covers (`thumbnail_source='upload'`) are used instead. `python manage.py import_story_thumbnails [--force]` stores sharp YouTube frames (banner auto-cropped) for JSON-LD and the video editor. Quick problem tagging in Staff > Reels & Shorts (42 videos still untagged).
- **Reviews**: site-wide Feedback button + dialog (`{% review_form %}`), public review or private feedback (stored without consent, never publishable). Staff "Reviews" (PatientReview) now mirror to the public stories page on publish (first name only, `sync_public_story`).
- **Review request**: `send_reminders` emails once per patient after N sessions (`BookingSettings.review_request_after_sessions`, 0 = off) linking to `/clinic/review/`. `ClinicProfile.google_review_url` (set to the Maps listing; replace with the Business Profile "Ask for reviews" link).
- **FAQ hub** `/clinic/faq/` with FAQPage JSON-LD; 15 drafts seeded unpublished by `scripts/seed_faqs.py` (doctor must check; publishing requires "Checked by").
- **Session packages** (Staff > Session packages, `packages.manage`); plans copy sittings/price/validity and show sittings left, paid, due, expiry.
- **Gallery** `/clinic/gallery/` (photos, uploaded videos ≤80 MB, YouTube/Instagram links, featured spotlight also on the home page). Seeded with the 4 Vijay Sethupathi visit photos (featured, label "Featured patient" as the clinic stated) and 2 clinic-front photos. Get written permission before promoting a celebrity's name/photos.
- **Courses/events**: `original_fees` (struck-out full price + % off, `components/price.html`); paid registrations require accepting `/clinic/terms/` (non-refundable fees), enforced server-side. `scripts/seed_programs.py` adds 3 courses + 3 events with the clinic's own photos (fees/dates to confirm).
- **GEO**: clinic JSON-LD now has PostalAddress parts, geo, hasMap and openingHours from doctor shifts.
- **Google reviews**: Google shows only 5 reviews without sign-in; all 5 are in `scripts/data/google_reviews.json`. All 113 need the Google Business Profile API (owner access).
- Fixed: reminders used the UTC date (missed early-morning appointments IST 00:00–05:30); inserted helpers had captured view decorators (caught by tests).

## Deployment (cPanel), 2026-10-21

- Build: `python scripts/export_content.py` (website content only: no patients/payments/staff) then `python scripts/build_release.py` -> `dist/spinalcure-cpanel.zip`. Guide: `deploy/CPANEL_GUIDE.md`. Server setup: `python deploy/setup_server.py` (charset check, migrate, cache table, collectstatic, media copy, loaddata on empty DB, first admin from .env).
- `deploy/.env.production` holds generated SECRET_KEY/FERNET_KEYS (git-ignored). Losing FERNET_KEYS = encrypted patient names unreadable.
- Production: PyMySQL fallback (no compiler on shared hosting), WhiteNoise + hashed static, MEDIA_ROOT/STATIC_ROOT from .env, secure cookies follow SECURE_SSL_REDIRECT, `passenger_wsgi.py` entry point. requirements.txt pinned to tested versions (Django 5.2.18, Python >= 3.10).
- Fixed for fresh databases: `spinalcure/migration_utils.py` now matches char(32) vs native uuid keys (fresh MariaDB 10.7+ failed with errno 150).
- Local MariaDB (XAMPP) service may be stopped; start it with `C:\xampp\mysql\bin\mysqld.exe --defaults-file=C:\xampp\mysql\bin\my.ini` (the service's data\my.ini path is wrong).
