# Deploying Spinal Cure on cPanel

This guide takes the zip file `spinalcure-cpanel.zip` to a live website. It takes about 30–45 minutes the first time.

In every command and path below, replace:

- `CPANELUSER` with your cPanel username (shown at the top right of cPanel and in File Manager paths like `/home/CPANELUSER`).
- `yourdomain.com` with your domain.

---

## 0. Check your hosting first

You need all of these. If one is missing, ask your hosting provider before starting.

| Requirement | Where to check in cPanel |
|---|---|
| **Setup Python App**, with Python **3.11 or 3.12** (3.10 is the minimum) | Software section |
| **MySQL Databases** (MySQL 5.7+/8, or MariaDB 10.5+) | Databases section |
| **Terminal** (or SSH access) | Advanced section |
| **Cron Jobs** | Advanced section |
| The domain points to this hosting account | Domains |

Shared plans with "Python App" are usually CloudLinux-based (for example Hostinger Business, A2, Namecheap Stellar Plus). Plain PHP-only plans cannot run this app.

---

## 1. Create the database

1. Open **cPanel → MySQL Databases**.
2. Under **Create New Database**, enter `spinalcure` and click **Create Database**. The full name becomes `CPANELUSER_spinalcure`.
3. Under **MySQL Users → Add New User**, enter the username `spinal`, generate a strong password, and **copy the password**. The full username becomes `CPANELUSER_spinal`.
4. Under **Add User To Database**, pick that user and that database, click **Add**, tick **ALL PRIVILEGES**, then click **Make Changes**.

Write down the full database name, the full username and the password. You need them in step 5.

---

## 2. Upload and extract the files

1. Open **cPanel → File Manager**. Go to your home folder (`/home/CPANELUSER`), **not** `public_html`.
2. Click **Upload** and choose `spinalcure-cpanel.zip` (about 58 MB). Wait until the upload reaches 100%.
3. Back in File Manager, right-click the zip, choose **Extract**, and confirm the folder `/home/CPANELUSER`.
4. You now have the folder `/home/CPANELUSER/spinalcure`. Inside it are `manage.py`, `passenger_wsgi.py`, `deploy/` and the other app folders. You can delete the zip file.

> The code stays outside `public_html` on purpose, so nobody can download the source code or the `.env` secrets.

---

## 3. Create the Python application

1. Open **cPanel → Setup Python App** and click **Create Application**.
2. Fill in the form:
   - **Python version:** 3.12 (or 3.11)
   - **Application root:** `spinalcure`
   - **Application URL:** your domain (leave the path after it empty)
   - **Application startup file:** `passenger_wsgi.py`
   - **Application Entry point:** `application`
   - **Passenger log file:** `/home/CPANELUSER/spinalcure/logs/passenger.log`
3. Under **Environment variables**, add `DJANGO_ENV` = `production`.
4. Click **Create**.
5. At the top of the app page, cPanel shows a command like the one below. **Copy it**; you need it in steps 4 and 6.
   ```
   source /home/CPANELUSER/virtualenv/spinalcure/3.12/bin/activate && cd /home/CPANELUSER/spinalcure
   ```

---

## 4. Install the packages

1. Open **cPanel → Terminal**.
2. Paste the command from step 3.5 and press Enter.
3. Run:
   ```
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
   This takes 2–5 minutes. It should end with `Successfully installed …` and no red **ERROR** lines.

> **No Terminal?** On the app page, go to **Configuration files**, add `requirements.txt` and click **Run Pip Install**.

---

## 5. Fill in the settings file (.env)

1. In File Manager, open `spinalcure/deploy/`, right-click `.env.production` and choose **Copy**. Copy it to `/home/CPANELUSER/spinalcure/.env` (the file name starts with a dot).
   - If you can't see dot-files, click **Settings** (top right) and tick **Show Hidden Files**.
2. Right-click the new `.env` and choose **Edit**. Change every line marked **CHANGE**:

| Setting | What to put |
|---|---|
| `ALLOWED_HOSTS` | `yourdomain.com,www.yourdomain.com` |
| `SITE_URL` | `https://yourdomain.com` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | the full names and password from step 1 |
| `MEDIA_ROOT` | `/home/CPANELUSER/public_html/media`. For an addon domain, use its document root instead (**cPanel → Domains** shows it). |
| `STATIC_ROOT` | `/home/CPANELUSER/spinalcure/staticfiles` |
| `SECURE_SSL_REDIRECT` | `False` for now (step 9 turns it on) |
| `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | a mailbox from **cPanel → Email Accounts** (create e.g. `noreply@yourdomain.com`; **Connect Devices** shows the server name and port 465) |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | leave empty: your existing accounts are imported with their current passwords (see step 6). Fill them in only if you want a brand-new admin instead. |

3. **Leave `SECRET_KEY` and `FERNET_KEYS` exactly as they are.** They were generated just for this site.
4. **Save a copy of the whole `.env` file somewhere safe outside the server**, for example a password manager. Patient names are encrypted with `FERNET_KEYS`; if that key is lost, nobody can ever read them again.

---

## 6. Run the setup

In **Terminal**, with the step 3.5 command already active, run:

```
python deploy/setup_server.py
```

It prints these steps, each ending without an error:

1. **Checking the configuration:** warnings are fine; errors are not.
2. **Database character set:** `utf8mb4: OK`, or it fixes the character set itself.
3. **Creating / updating database tables:** about 100 lines of "Applying …".
4. **Collecting static files**
5. **Copying website images:** `910 files copied`.
6. **Loading your data:** `Installed 537 object(s)`. This is the clinic profile, practitioners, **your staff accounts with the same sign-in details**, staff profiles and ID cards, ID-card branding, doctor availability and booking rules, plus the website content (Google reviews, videos, gallery, FAQs, translations).
7. **First admin account:** `An admin already exists: skipped.` (your imported accounts). If it says to set `ADMIN_EMAIL`, the data file was missing.

Then:

1. Go back to **Setup Python App** and click **Restart** on the app.
2. Make sure `ADMIN_PASSWORD` is **not** in `.env`.

---

## 7. Check the site

1. Open `http://yourdomain.com` and check that the home page loads with images, in English.
2. Use the language switcher to change to தமிழ் and check that it switches.
3. Sign in at `http://yourdomain.com/en/accounts/login/` with the same email and password you use locally. **Change that password now** (profile menu → Settings), because it was typed on a development machine.
4. Go to **Clinic Setup** and check the phone numbers, address and Google review link.
5. Go to **Team Accounts** and create the staff accounts (doctor, receptionist…). Each person gets their own login.

**Not included:** patients, payments and reports, expenses, appointments, courses, batches, students and events. The site starts clean; add those on the live site.

`deploy/content.json` contains your password hashes. Keep the zip private and delete `deploy/content.json` from the server after setup if you like (the data is already in the database).

---

## 8. Scheduled jobs (reminders, emails, payments)

Open **cPanel → Cron Jobs** and add these three. In each, replace `3.12` if you chose another Python version.

| Common setting | Command |
|---|---|
| Every 5 minutes (`*/5 * * * *`) | `cd /home/CPANELUSER/spinalcure && /home/CPANELUSER/virtualenv/spinalcure/3.12/bin/python manage.py send_reminders >> logs/cron.log 2>&1` |
| Every 5 minutes (`*/5 * * * *`) | `cd /home/CPANELUSER/spinalcure && /home/CPANELUSER/virtualenv/spinalcure/3.12/bin/python manage.py process_notifications >> logs/cron.log 2>&1` |
| Every 15 minutes (`*/15 * * * *`) | `cd /home/CPANELUSER/spinalcure && /home/CPANELUSER/virtualenv/spinalcure/3.12/bin/python manage.py reconcile_razorpay >> logs/cron.log 2>&1` |
| Every hour (`0 * * * *`) | `cd /home/CPANELUSER/spinalcure && /home/CPANELUSER/virtualenv/spinalcure/3.12/bin/python manage.py sync_youtube >> logs/cron.log 2>&1` |

What the jobs do:
- **`send_reminders`:** appointment and event reminders, treatment follow-ups, missed appointments, and the "how was your treatment" review request.
- **`process_notifications`:** sends queued emails and retries failed ones.
- **`reconcile_razorpay`:** only needed once Razorpay is set up.
- **`sync_youtube`:** pulls new videos and Shorts (title + caption) from the YouTube channel set in Clinic Settings. Staff can also press **Sync from YouTube** on the Reels & Shorts page.

---

## 9. Turn on HTTPS

1. Open **cPanel → SSL/TLS Status**, tick your domain and `www`, and click **Run AutoSSL**. Wait until both show a green lock (a few minutes, sometimes up to an hour).
2. In `.env`, set `SECURE_SSL_REDIRECT=True`.
3. Restart the app in **Setup Python App**.
4. Open `http://yourdomain.com`. It should redirect to `https://` automatically.

---

## 10. Online payments (when the Razorpay KYC is approved)

1. In the Razorpay dashboard, go to **Account & Settings → API Keys** and generate **live** keys.
2. Put them in `.env` as `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`.
3. In the Razorpay dashboard, go to **Webhooks → Add**:
   - **URL:** `https://yourdomain.com/payments/razorpay/webhook/`
   - **Events:** `payment.captured`, `order.paid`, `payment.failed`, `refund.processed`, `refund.failed`
   - **Secret:** make one up, and put the same value in `.env` as `RAZORPAY_WEBHOOK_SECRET`.
4. Restart the app.
5. Test with a small real payment on an invoice ("Create payment link").

---

## 11. Updating the site later

1. Build a new zip on the development computer:
   ```
   python scripts/export_content.py
   python scripts/build_release.py
   ```
   The zip appears in `dist/spinalcure-cpanel.zip`.
2. Upload it to `/home/CPANELUSER` and extract it, overwriting the old files. Your `.env` and uploaded photos are not in the zip, so they are kept.
3. In Terminal (step 3.5 command first), run:
   ```
   pip install -r requirements.txt
   python deploy/setup_server.py
   ```
   It applies database changes and new static files. Existing website content is left alone, because the content you edit on the live site is the real one now.
4. Click **Restart** in Setup Python App.

---

## 12. Backups

- **cPanel → Backup:** download a full backup (or at least the database and `public_html/media`) every week. Many hosts also do this automatically; check with them.
- Keep the `.env` file (with `FERNET_KEYS`) in a safe place outside the server.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "Incomplete response" / 500 error | Read `spinalcure/logs/passenger.log` and `spinalcure/logs/django.log` in File Manager; the last lines name the problem. Common causes are a typo in `.env`, or packages not installed (step 4). |
| `FERNET_KEYS must be set…` | `.env` is missing, misnamed (it must be exactly `.env`), or not in `/home/CPANELUSER/spinalcure`. |
| `Access denied for user` | Wrong DB name, user or password in `.env`, or the user wasn't added to the database (step 1.4). Use the full names with the `CPANELUSER_` prefix. |
| Page has no styling | Run `python deploy/setup_server.py` again (it collects static files), then restart the app. |
| Photos don't show | `MEDIA_ROOT` must be inside the domain's document root (`public_html/media`), and the setup must have run. |
| Tamil text shows as `????` | The database wasn't utf8mb4 when the tables were created. Empty the database (phpMyAdmin → drop all tables) and run the setup again. |
| Login page reloads without signing in | You are on `http://` while `SECURE_SSL_REDIRECT=True`. Finish step 9, or set it back to `False` until the certificate is ready. |
| After any `.env` change | Always click **Restart** in Setup Python App. |
