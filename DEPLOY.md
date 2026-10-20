# Deploying SpinalCure

`DJANGO_ENV` defaults to **production**. Use `DJANGO_ENV=development` for local work.

## 1. Required environment (production)

| Variable | Notes |
|---|---|
| `SECRET_KEY` | long random string |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL` | your domain(s) |
| `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | MySQL |
| `FERNET_KEYS` | **required**; the server refuses to start with the key that was once committed to git. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | SMTP. Without it, email deliveries are recorded as failed and retried, never silently dropped |
| `CACHE_LOCATION` | optional Redis URL. Empty = database cache (run `createcachetable`) |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | optional; online payment links. Webhook URL: `https://<domain>/payments/razorpay/webhook/` with events `payment.captured`, `order.paid`, `payment.failed`, `refund.processed`, `refund.failed`. `RAZORPAY_LINK_TTL_HOURS` (default 168) sets link expiry |
| `NOTIFY_SMS_BACKEND`, `NOTIFY_WHATSAPP_BACKEND` | optional dotted path to a provider class (`send(to, text)`); unset = those channels are marked *skipped* |

## 2. First deploy

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createcachetable        # only if CACHE_LOCATION is empty
python manage.py collectstatic --noinput
```

System package for correct Indic-script rendering in ID cards and PDFs: **libraqm** (HarfBuzz/FriBidi).
Fonts are bundled in `static/fonts` (SIL OFL).

If you had data encrypted under the old key: set `FERNET_KEYS=<new>,<old>` then `python manage.py reencrypt_data`, then drop the old key.

## 3. Scheduled jobs (cron, every 5 minutes; no Redis/Celery needed)

```cron
*/5 * * * * cd /srv/spinalcure && python manage.py send_reminders
*/5 * * * * cd /srv/spinalcure && python manage.py process_notifications
*/15 * * * * cd /srv/spinalcure && python manage.py reconcile_razorpay
```

`send_reminders` queues appointment/event reminders, follow-ups and missed-appointment handling.
`process_notifications` delivers pending notifications and retries failed ones with back-off.
`reconcile_razorpay` records captured online payments whose webhook was missed (safe to run repeatedly).

## 4. Frontend assets

Everything is self-hosted (no CDN at runtime): Alpine, HTMX, Bootstrap Icons, Tom Select, Chart.js, FullCalendar,
html2canvas, jsPDF and the web fonts live in `static/`. The UI kit (tokens, light/dark theme, components) is defined in `theme/static_src/tailwind.config.js` and `src/styles.css`; its markup is in `templates/ui/` (reference page: `/ui-kit/`), behaviour in `static/js/ui.js`. After changing either file run `npm run build` in `theme/static_src`. Tailwind is compiled to `static/css/tailwind.css` and **committed**.
After adding new utility classes to templates, rebuild it:

```bash
cd theme/static_src && npm install && npm run build
```

## 5. Translations (EN / TA / HI / TE / ML / KN)

`.mo` files are committed (production has no `msgfmt`).

```bash
python scripts/i18n_extract.py      # update locale/*.po from code and templates
python scripts/i18n_batch.py list   # untranslated strings;  apply <batch.json> to fill them
python scripts/i18n_compile.py      # rebuild .mo
```

The Tamil/Hindi/Telugu/Malayalam/Kannada text was drafted by an AI assistant and **needs review by native speakers**, especially medical wording.

### Website content (clinic details, blog, reviews, events, names...)

Managed in the staff area under **Translations** (English is the source; per-language coverage %, auto-translate, edit/review).
Provider is picked from env: `ANTHROPIC_API_KEY` (best, transliterates names; `ANTHROPIC_MODEL` optional) → `GOOGLE_TRANSLATE_API_KEY` →
free MyMemory (no key, ~5,000 chars/day, `MYMEMORY_EMAIL` raises it; set `TRANSLATION_FREE=0` to disable). Use a shared cache
(`CACHE_BACKEND`, e.g. Redis) if you run several workers, otherwise edits take up to 60 s to appear on other workers.

## 6. Search engines (SEO)

* Set `SITE_URL` to the public https origin (e.g. `https://www.example.in`): canonical, hreflang, Open Graph and the
  sitemap are built from it, never from the request's Host header. Set `SEO_ALLOW_INDEXING=False` on staging
  (robots.txt then disallows everything); `DEBUG=True` does the same.
* `/robots.txt` and `/sitemap.xml` (pages, articles, practitioners, events, courses; each URL lists all six languages
  plus `x-default`). Only public pages are indexable; every other response carries `X-Robots-Tag: noindex, nofollow`.
* JSON-LD: `MedicalClinic` (home, about), `Person` (practitioner), `BlogPosting` + breadcrumbs, `Event`, `Course`,
  `VideoObject` (patient-story videos with a thumbnail). No rating/review markup: Google ignores self-serving reviews
  for clinics. Fill in the clinic profile (address, phone, logo, social links): empty fields are left out, not invented.
* Removed content answers `410 Gone` (an article that was published then unpublished, a deactivated practitioner); the
  old home URL `/<lang>/clinic/portfolio/` redirects permanently to `/<lang>/`.
* After go-live: verify the domain in **Google Search Console** and **Bing Webmaster Tools** (DNS TXT record), submit
  `https://<domain>/sitemap.xml` in both, run a few URLs through the URL Inspection tool and
  https://search.google.com/test/rich-results, and check *Pages* / *Enhancements* after a few days. Create or claim the
  **Google Business Profile** with the same name, address and phone as the clinic profile (local ranking depends on it,
  not on this code). No setting here guarantees rankings.

## 7. Tests

```bash
export DJANGO_SETTINGS_MODULE=spinalcure.settings.test
pytest --maxfail=1000 --ignore=tests/browser --ignore=tests/integration/test_migrations.py
pytest --migrations --create-db tests/integration/test_migrations.py   # real migrations (pytest.ini defaults to --nomigrations)
pytest --maxfail=1000 tests/browser                                    # Chromium via Playwright
```

The tests run on SQLite. Row-locking/booking concurrency has been exercised on SQLite only; validate on MySQL before go-live.
