# Spinal Cure: project overview

Clinic management system and public website for **Spinal Cure, Arumbakkam, Chennai** (Dr. R. Basheer Basha, classical acupuncture and spine care). One Django app serves two audiences: patients and visitors (public site and patient portal) and clinic staff (admin app).

For environment traps and open work, see [PROJECT_MEMORY.md](PROJECT_MEMORY.md). For deployment, see [DEPLOY.md](DEPLOY.md). The UI brief is in [DESIGN_PROMPT.md](DESIGN_PROMPT.md).

---

## 1. Tech stack

| Layer | Choice |
|---|---|
| Backend | Django (pinned 4.2.*, runs on 5.x), Django REST Framework, SimpleJWT, drf-spectacular (Swagger at `/api/schema/swagger/`) |
| Database | MariaDB/MySQL (`mysqlclient`); SQLite for tests |
| Cache and sessions | Redis in production (`django-redis`), DB sessions otherwise |
| Frontend | Server-rendered Django templates, Tailwind 3 (`django-tailwind`, built in `theme/static_src`), Alpine.js, htmx, Tom Select, Chart.js, Bootstrap Icons |
| UI kit | Radix-style kit in plain Tailwind and Alpine: `.btn`, `.card`, `.badge`, `.ui-table`, `.menu`, `.dialog`, `.tabs`, `.dropzone`, `.toast` |
| Theming | CSS-variable tokens, clinical green, light and dark (staff), light only (public) |
| i18n | Django gettext (`en, ta, hi, te, ml, kn`), `polib` tooling in `scripts/i18n_*.py`, Noto fonts per script |
| Documents | ReportLab (PDF with Indic shaping), Pillow (ID card PNG), `openpyxl` (Excel), `qrcode` |
| Payments | Razorpay over stdlib HTTPS (`payments/razorpay.py`) |
| Translation providers | Anthropic, then Google Translate, then MyMemory (free, daily quota) |
| Security | `cryptography` (Fernet-encrypted fields), `pyotp`, `django-ratelimit`, CORS headers |
| Logging | `python-json-logger` |
| Tests | pytest, pytest-django, Playwright (browser tests in `tests/browser`) |

---

## 2. Apps

| App | Responsibility |
|---|---|
| `accounts` | Custom user, roles, staff profile, login, settings, user admin |
| `clinic` | Clinic profile, practitioners, public site content, blog, testimonials and videos, problem categories, content translations, activity log |
| `patients` | Patients, treatment plans, sessions, diagnosis, reviews, patient portal (OTP login) |
| `appointments` | Calendar, list, availability and leave, slot engine, public booking, token-based manage page |
| `payments` | Receipts and invoices, expenses, refunds, reports, Razorpay online payments |
| `courses` | Training courses, batches, registrations, waitlist, feedback |
| `events` | Public events and classes, registrations, waitlist, `.ics` calendar, feedback |
| `idcards` | Staff and owner ID cards: issue, branding, PNG and PDF render, QR verify, share links |
| `notifications` | In-app bell and centre, email and SMS delivery log, per-user preferences |
| `analytics` | Dashboard and stats API |
| `spinalcure` | Settings (base, dev, staging, production, test), RBAC matrix, encrypted fields, upload paths, language list |

---

## 3. Roles and permissions

Central matrix in [spinalcure/rbac.py](spinalcure/rbac.py). Every view and export checks a capability. `is_staff` grants nothing.

| Role | Can do |
|---|---|
| Super Admin | Everything, including clinical data and the activity log |
| Clinic Admin | Management plus user accounts (but not clinical notes) |
| Owner | Management: billing, refunds, expenses, reports, website, ID cards, events |
| Doctor | Patients, clinical notes, schedule, reviews, billing view |
| Receptionist | Patients, appointments, take payments, event registrations |
| Staff | Minimal home screen only |

Patients are not user accounts. They sign in to the portal with a one-time code (OTP).

---

## 4. Features

### Public website
- Home, About, practitioner profile, conditions treated, treatment process, contact and map.
- **Patient Stories:** real Google reviews plus Instagram reels and YouTube Shorts. Search by problem dropdown or keyword. Visitors can submit a review (saved unpublished until staff approve).
- Appointment booking with live free slots, by email or phone, with a confirmation email.
- Health blog with tags, courses, public events, `.ics` downloads, registration with waitlist.
- Online payment page (Razorpay): UPI, cards, net banking, wallets.
- Language switcher: English, Tamil, Hindi, Telugu, Malayalam, Kannada.

### Patient portal
OTP login, dashboard with appointments, sessions and payments, and a token link to view or change a booking.

### Clinical and front desk
- Patients with encrypted names, attender and emergency details, blood group, photo and printable card.
- Treatment plans, sessions with PIN-gated access and a PDF note, diagnosis (case sheet and TCM).
- Appointment calendar and list with collision check, doctor shifts, leave and clinic holidays.

### Finance
- Receipts and invoices with GST, partial payments and PDF download.
- Refunds, expenses, and a payments report (collections, GST, refunds, outstanding, profit).
- Razorpay payment link from any invoice, webhook-confirmed and idempotent.
- Exports on every list: Excel, CSV, PDF, copy, print.

### Education and events
Courses with batches, registrations, waitlist promotion, cancellation and feedback. Events with live or online status, registration actions and feedback.

### Content and reputation
Reviews, curated testimonials, reels and Shorts, problem categories, blog and tags. **Website Translations** screen with per-language % translated, auto-translate and staff editing.

### ID cards
Vertical card with a yin-yang back and the "Without Surgery, Without Medicine and Without Diet" quote. Front: photo, name, designation, gender, DOB, blood group, contact, address, QR. Back: clinic address, website, contact. PNG and PDF, public verify page, share link, reissue and revoke.

### Platform
Notification centre (in-app, email, SMS) with delivery log and retry, command search (Ctrl K), activity log with revert, dark mode, rate limiting, and an audit trail.

---

## 5. Pages and URLs

### Public (no login)

| Page | URL |
|---|---|
| Home | `/clinic/portfolio/` |
| About | `/clinic/about/` |
| Practitioner | `/clinic/practitioners/<id>/` |
| Patient Stories | `/clinic/testimonials/` |
| Blog | `/clinic/blog/`, `/clinic/blog/<slug>/` |
| Courses | `/clinic/courses/<id>/` |
| Events | `/clinic/events/`, `/clinic/events/<id>/` |
| Registration manage | `/clinic/events/registration/<token>/`, `/clinic/courses/registration/<token>/` |
| Booking manage | `/appointments/manage/<token>/` |
| Online pay | `/payments/pay/<token>/` |
| ID card verify and share | `/idcards/verify/<card_id>/`, `/idcards/share/<token>/` |
| Patient portal | `/patients/portal/login/`, `/verify/`, `/dashboard/` |
| Login | `/accounts/login/` |

All routes are prefixed with the language code (for example `/en/`, `/ta/`).

### Staff

| Area | Screens |
|---|---|
| Overview | Dashboard (`/analytics/dashboard/`), notifications |
| Clinical | Appointments (calendar and list), Availability, Patients (list, detail, create, edit), sessions, plans |
| Financials | Payments, Payment create, Invoice, Payments report, Expenses |
| Education | Courses, batches, registrations, feedback; Events, registrations, feedback |
| Content and reputation | Reviews, Testimonials, Reels and Shorts, Problem Categories, Health Blog, Tags, Website Translations |
| Administration | Practitioners, Staff users, ID cards (dashboard, issue, branding, mine), Clinic setup, Settings, Activity log |
| Developer | `/ui-kit/` component reference (super admin) |

### API
REST under `/api/` (patients, appointments, payments, clinic, analytics), JWT auth, schema at `/api/schema/`.

---

## 6. Project flow

### 6.1 Patient journey

```
Visitor lands on public site
   -> reads real reviews / watches reels (filter by problem)
   -> books appointment (free slots from doctor shifts minus leave and existing bookings)
   -> confirmation email with manage link (reschedule or cancel by token)
   -> visits clinic; receptionist registers or finds the patient
   -> doctor records diagnosis, treatment plan, sessions
   -> receptionist raises a receipt or invoice
        -> paid at the desk (cash, UPI, card, cheque, transfer)
        -> or Razorpay link sent by email; patient pays online
   -> receipt email and PDF
   -> follow-up reminder; portal shows history
   -> happy patient submits a review; staff approve it; it appears on Patient Stories
```

### 6.2 Appointment and slot flow

```
Practitioner shifts (weekly) + time off + clinic closures
        -> slot engine -> available slots for a date
Public booking or staff booking -> collision check -> appointment saved
        -> notification events: booked, confirmed, rescheduled, cancelled, reminder, missed
```

### 6.3 Online payment flow (Razorpay)

```
Staff: invoice -> "Create payment link" -> OnlineOrder + secure token URL
Payer: opens /payments/pay/<token>/ -> Razorpay Checkout
Razorpay -> browser callback -> server verifies HMAC signature -> mark_paid (idempotent)
Razorpay -> webhook (payment.captured, order.paid) -> HMAC check -> mark_paid (same path)
mark_paid -> payment updated -> receipt email -> staff notification
```

### 6.4 Multilingual content flow

```
Staff writes English content (clinic text, services, blog, courses, names)
   -> Website Translations screen shows % per language
   -> "Auto-translate missing" (Anthropic -> Google -> MyMemory)
   -> statuses: missing / auto / edited / final / stale (English changed)
   -> staff edit or mark final; edits are never overwritten
   -> public site renders the visitor's language, falling back to English
UI strings: {% trans %} -> i18n_extract -> i18n_batch apply -> i18n_compile
```

### 6.5 ID card flow

```
Staff user exists -> Issue card (choose what shows) -> card ID + QR
   -> view PNG front/back, PDF, "My ID card"
   -> optional public share link (name, role, status only)
   -> anyone scans QR -> /idcards/verify/<id>/ -> Active / Revoked / Expired
   -> reissue or revoke at any time
```

### 6.6 Notification flow

```
Domain event (e.g. payment_received) -> notifications.service
   -> per-user preference + event defaults -> channels: in-app, email, SMS
   -> delivery log with status and retry
```

---

## 7. Security model

- Least-privilege capability checks on all views, exports, calendar, search and deletes.
- Patient names and sensitive JSON fields encrypted at rest (Fernet).
- PIN-gated access to clinical session notes.
- Rate limits on login, OTP, public forms and review submission; honeypot on public forms.
- Public reviews are unpublished by default.
- HMAC verification on Razorpay callback and webhook.
- Stored values escaped in templates; `json_script` for data passed to JS.
- Random file names for private uploads.
- Production refuses to start without `FERNET_KEYS`; `DJANGO_ENV` defaults to production.

---

## 8. Repository layout

```
accounts/ clinic/ patients/ appointments/ payments/ courses/ events/
idcards/ notifications/ analytics/        Django apps
spinalcure/                                settings, urls, rbac, fields, uploads, languages
templates/  static/  theme/static_src/     shared templates, assets, Tailwind source
locale/                                    en, ta, hi, te, ml, kn catalogues
scripts/                                   seed_real_data, seed_demo_users, i18n_* tools
tests/                                     unit, integration, browser
```

## 9. Run it

```bash
DJANGO_ENV=development python manage.py migrate
DJANGO_ENV=development python manage.py runserver 127.0.0.1:8001 --noreload
cd theme/static_src && npm run build          # rebuild Tailwind
DJANGO_SETTINGS_MODULE=spinalcure.settings.test pytest --ignore=tests/browser \
  --ignore=tests/integration/test_migrations.py -q
```

On Windows set `PYTHONUTF8=1` for Indic text.
