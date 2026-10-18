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
| `NOTIFY_SMS_BACKEND`, `NOTIFY_WHATSAPP_BACKEND` | optional dotted path to a provider class (`send(to, text)`); unset = those channels are marked *skipped* |

## 2. First deploy

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createcachetable        # only if CACHE_LOCATION is empty
python manage.py collectstatic --noinput
```

System package for correct Tamil/Hindi/Arabic rendering in ID cards and PDFs: **libraqm** (HarfBuzz/FriBidi).
Fonts are bundled in `static/fonts` (SIL OFL).

If you had data encrypted under the old key: set `FERNET_KEYS=<new>,<old>` then `python manage.py reencrypt_data`, then drop the old key.

## 3. Scheduled jobs (cron, every 5 minutes; no Redis/Celery needed)

```cron
*/5 * * * * cd /srv/spinalcure && python manage.py send_reminders
*/5 * * * * cd /srv/spinalcure && python manage.py process_notifications
```

`send_reminders` queues appointment/event reminders, follow-ups and missed-appointment handling.
`process_notifications` delivers pending notifications and retries failed ones with back-off.

## 4. Frontend assets

Everything is self-hosted (no CDN at runtime): Alpine, HTMX, Bootstrap Icons, Tom Select, Chart.js, FullCalendar,
html2canvas, jsPDF and the web fonts live in `static/`. Tailwind is compiled to `static/css/tailwind.css` and **committed**.
After adding new utility classes to templates, rebuild it:

```bash
cd theme/static_src && npm install && npm run build
```

## 5. Translations (EN / TA / HI / AR)

`.mo` files are committed (production has no `msgfmt`).

```bash
python scripts/i18n_extract.py      # update locale/*.po from code and templates
python scripts/i18n_batch.py list   # untranslated strings;  apply <batch.json> to fill them
python scripts/i18n_compile.py      # rebuild .mo
```

The Tamil/Hindi/Arabic text was drafted by an AI assistant and **needs review by native speakers**, especially medical wording.

## 6. Tests

```bash
export DJANGO_SETTINGS_MODULE=spinalcure.settings.test
pytest --maxfail=1000 --ignore=tests/browser --ignore=tests/integration/test_migrations.py
pytest --migrations --create-db tests/integration/test_migrations.py   # real migrations (pytest.ini defaults to --nomigrations)
pytest --maxfail=1000 tests/browser                                    # Chromium via Playwright
```

The tests run on SQLite. Row-locking/booking concurrency has been exercised on SQLite only; validate on MySQL before go-live.
