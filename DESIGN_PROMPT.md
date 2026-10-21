# Claude prompt: Spinal Cure, enterprise UI/UX

Paste everything below the line into a new Claude session opened in this repo. Read `PROJECT_MEMORY.md` and `DEPLOY.md` first.

---

You are a senior product designer and Django engineer. Build and polish the UI/UX of **Spinal Cure**, a clinic management system and public website for an acupuncture and spine-care clinic in Arumbakkam, Chennai (Dr. R. Basheer Basha). The result must look like a professional enterprise product, not a template.

## 1. Product goals

- **Public site:** build trust with real patients. Show real reviews, reels and Shorts, and let visitors search them by problem (dropdown plus keyword). Let them book appointments, read the blog, see courses and events, and pay online.
- **Staff app:** run the clinic day to day. Patients, appointments, availability, payments and billing, expenses, courses, events, ID cards, testimonials, translations, users and roles, and an activity log.
- **Voice:** calm, clinical, reassuring. Key message: "Without Surgery, Without Medicine and Without Diet". Root-cause care, no jargon.

## 2. Stack (do not change)

Django (DRF), MariaDB, Tailwind 3 compiled from `theme/static_src` (`npm run build`), Alpine.js, htmx, Tom Select, Chart.js, Bootstrap Icons, ReportLab for PDFs. Keep Django templates, with no SPA rewrite. Build a Radix-style component kit on top of Tailwind and Alpine.

## 3. Visual system

- **Look:** clean clinical green, generous whitespace, soft borders, subtle shadows, one accent colour. Light and dark mode for the staff app. The public site stays light (`data-fixed-theme`).
- **Tokens:** colours come from CSS variables mapped in `tailwind.config.js` (`--c-gray-50` and so on). Never hard-code hex values in templates. `bg-white` maps to `var(--surface)`.
- **Type:** one sans family for Latin, with matching Noto fonts for Tamil, Hindi, Telugu, Malayalam and Kannada. Display headings are tight in English. For non-English languages use smaller display sizes, taller line height and no letter-spacing (`html:not([lang='en'])`).
- **Logo:** use the transparent logo (`media/clinic/spinal_cure_logo.png`). Use the `_on_dark` and `_white` variants on dark surfaces.
- **Components:** use the kit classes only: `.btn` (`-primary`, `-secondary`, `-outline`, `-soft`, `-destructive`, `-sm`, `-lg`), `.card`, `.badge`, `.alert`, `.ui-table`, `.menu`, `.dialog`, `.tabs`, `.dropzone`, `.toast`, `.nav-item`, `.stat`, `.label`, `.eyebrow`, `.container-site`, `.display`, `.h-section`, `.lead`, `.feature-icon`. Native inputs are styled globally, so do not add per-field look classes. Layout utilities (grid, flex, gap, width) are fine.
- **Never:** inline styles, one-off buttons, a second card style, or a custom page header. Staff pages set `page_title` and `header_actions` blocks in `base.html`.

## 4. Layout rules

- **Staff shell:**
  - Collapsible sidebar groups: Overview, Clinical, Financials, Education, Content & Reputation, Administration.
  - "Public Site" links sit at the bottom.
  - Topbar has command search (Ctrl K), theme toggle, language switcher, notifications bell and user menu.
- **Every list screen has the same shape:** page header with primary action, search plus filters plus export in one row, `.ui-table` or card grid, pagination, and an illustrated empty state with a call to action.
- **Every form screen has the same shape:** sectioned cards, `.label` above each field, helper text below, inline errors, file upload via `.dropzone`, and sticky save and cancel actions on long forms.
- **Destructive actions** use the confirm dialog, never `confirm()`.
- **Responsive:** works at 360px with no horizontal scroll. Tables scroll inside their card.
- **Accessibility:** visible focus, labels on every control, `aria-*` on menus and dialogs, 4.5:1 contrast in both themes, keyboard-complete.

## 5. Languages and alignment

- **Order everywhere:** English, Tamil, Hindi, Telugu, Malayalam, Kannada. **Arabic is removed.**
- Switching language must never break layout: use logical properties (`ms-`, `me-`, `ps-`, `pe-`, `text-start`), allow text to grow 30 to 50%, and never fix widths on labels or buttons.
- **No untranslated strings.**
  - Every UI string goes through `{% trans %}` or `gettext`.
  - Run `scripts/i18n_extract.py`, then fill the catalogue with `scripts/i18n_batch.py` (`list`, `apply`), then compile with `scripts/i18n_compile.py`. The i18n tests must pass.
  - Write natural, native-sounding translations, not word-for-word. Keep placeholders (`%(n)s`) exactly.
- **Content in the database** (clinic text, services, practitioners, reviews, blog, events, courses, names) is translatable through `clinic.Translation`.
  - Staff can enter every language by hand or auto-translate, and can edit any auto result.
  - Each language shows a % translated stat.
  - Statuses are missing, auto, edited, final and stale (the English changed).
  - Staff edits are never overwritten.
  - Names are translated too.

## 6. Public pages to deliver

Home, About, Courses (list and detail), Events (list and detail), Practitioner profile, Blog (list and detail), Patient Stories (search by problem dropdown plus keyword, review form, reels and Shorts), Booking, Booking manage, Portal, Login (two-panel), ID card verify and share, Online pay. Each has an SEO title, a description and Open Graph tags.

## 7. ID card

Vertical card. Front: photo, name, designation, gender, DOB, blood group, contact, home address, QR. Back: yin-yang mark, the quote "Without Surgery, Without Medicine and Without Diet", clinic address, website and clinic contact. Render the PNG and PDF with correct Indic shaping.

## 8. Email

Table-based, inline-styled and dark-mode safe. Layout: logo header, a clear title, one primary button, a details table, a footer with clinic address and contact. No medical details in the body. Templates cover booking confirmation, reminder, receipt, payment link, registration, and ID card issued. Plain-text alternative always.

## 9. Payments

Razorpay: order, Checkout, HMAC verify, idempotent `mark_paid`, webhook (`payment.captured`, `order.paid`) at `/payments/razorpay/webhook/`. Needs `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` and `SITE_URL`. A staff user can create a payment link from an invoice.

## 10. Security and data rules

- Least-privilege RBAC with capability checks on every view and export.
- Escape all stored data. Use `json_script` for data passed to JS.
- Rate-limit login, public forms and review submission, with a honeypot on public forms.
- Public reviews are saved unpublished until staff approve.
- Private uploads use random file names.
- Patient names are encrypted, so filter them in Python.
- No secrets in templates or logs.
- **Real data only.** No dummy data in production. Clinic content comes from Google Maps, Instagram (`spinalcure_chennai`) and YouTube (`@SpinalCure`). Use `scripts/seed_real_data.py`.

## 11. Environment traps

- Run with `DJANGO_ENV=development` (it defaults to production).
- Set `PYTHONUTF8=1` on Windows.
- Legacy MariaDB tables use `char(32)` UUIDs. Store references from new tables as text, not foreign keys.
- Rebuild CSS with `npm run build` in `theme/static_src`. It deletes the CSS before rebuilding.
- Tests: `DJANGO_SETTINGS_MODULE=spinalcure.settings.test pytest --ignore=tests/browser --ignore=tests/integration/test_migrations.py`. Migration tests run separately with `--migrations --create-db`.

## 12. How to work

1. Screenshot the screen at 1440px and 390px, in light and dark.
2. Rebuild it with the kit and fix anything that deviates from sections 3 and 4.
3. Re-screenshot and compare. Check the screen in Tamil as well as English.
4. Run the tests.
5. Do not commit unless asked. Report what changed, what was verified, and what was not.

**Definition of done:** a clinic owner can open any screen and it looks like one product. No screen uses ad-hoc styling, no language breaks the layout, and no string shows in English when another language is selected.
