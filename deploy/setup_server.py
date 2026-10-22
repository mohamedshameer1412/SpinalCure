"""One-time (and safe to repeat) server setup for cPanel.

Run from the application root with the app's Python (cPanel Terminal, or "Execute python script" in Setup Python App):

    python deploy/setup_server.py

It: checks the .env, creates the tables (migrate), the cache table, collects static files, copies the website
images into MEDIA_ROOT, loads the website content on an empty database, and creates the first admin account
from ADMIN_EMAIL / ADMIN_PASSWORD in .env (only if no admin exists yet).
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault('DJANGO_ENV', 'production')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'spinalcure.settings')


def step(msg):
    print(f'\n==> {msg}', flush=True)


if not (ROOT / '.env').exists():
    sys.exit('No .env file in the application root. Copy deploy/.env.production to .env and fill it in first.')

import django  # noqa: E402

django.setup()
from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.management import call_command  # noqa: E402
from decouple import config  # noqa: E402

step('Checking the configuration')
call_command('check', '--deploy', '--fail-level', 'ERROR')

step('Database character set (Tamil, Hindi, Telugu, Malayalam and Kannada need utf8mb4)')
from django.db import connection  # noqa: E402
if connection.vendor == 'mysql':
    with connection.cursor() as cur:
        cur.execute('SELECT @@character_set_database')
        charset = cur.fetchone()[0]
        if charset != 'utf8mb4':
            cur.execute(f'ALTER DATABASE `{connection.settings_dict["NAME"]}` '
                        'CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
            print(f'Changed the database default from {charset} to utf8mb4.')
        else:
            print('utf8mb4: OK')

step('Creating / updating database tables')
call_command('migrate', interactive=False)
call_command('createcachetable')

step(f'Collecting static files into {settings.STATIC_ROOT}')
call_command('collectstatic', interactive=False, verbosity=0)

step(f'Copying website images into {settings.MEDIA_ROOT}')
src, dst = ROOT / 'deploy' / 'media', Path(settings.MEDIA_ROOT)
copied = 0
for f in src.rglob('*') if src.exists() else []:
    if f.is_file():
        target = dst / f.relative_to(src)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            copied += 1
print(f'{copied} files copied (existing files are never overwritten)')

psrc, pdst = ROOT / 'deploy' / 'private_media', Path(settings.PRIVATE_MEDIA_ROOT)
p_copied = 0
for f in psrc.rglob('*') if psrc.exists() else []:
    if f.is_file():
        target = pdst / f.relative_to(psrc)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            p_copied += 1
print(f'{p_copied} private staff photos copied to {pdst}')

# Uploads must never run as code or be listed. php_flag would break PHP-FPM hosts, so handlers are removed instead.
(dst / '.htaccess').write_text(r'''# Written by deploy/setup_server.py: uploaded files are data only.
Options -Indexes -ExecCGI
RemoveHandler .php .phtml .php3 .php4 .php5 .php7 .php8 .phar .pl .py .cgi .sh .asp .aspx .jsp
RemoveType .php .phtml .php3 .php4 .php5 .php7 .php8 .phar .pl .py .cgi .sh .asp .aspx .jsp
<FilesMatch "\.(php\d?|phtml|phar|pl|py|cgi|sh|asp|aspx|jsp|html?|svg|shtml)$">
    Require all denied
</FilesMatch>
<IfModule mod_headers.c>
    Header set X-Content-Type-Options "nosniff"
</IfModule>
''', encoding='utf-8')
print(f'Upload hardening written to {dst / ".htaccess"}')
print(f'Private files (patient/staff photos, receipts) live in {settings.PRIVATE_MEDIA_ROOT}, outside the web folder.')

step('Loading website content')
from clinic.models import ClinicProfile  # noqa: E402
if ClinicProfile.objects.exists():
    print('Content already present: skipped (your edits are kept).')
else:
    call_command('loaddata', str(ROOT / 'deploy' / 'content.json'))

step('First admin account')
User = get_user_model()
email, password = config('ADMIN_EMAIL', default=''), config('ADMIN_PASSWORD', default='')
if User.objects.filter(is_superuser=True).exists():
    print('An admin already exists: skipped.')
elif not (email and password):
    print('Set ADMIN_EMAIL and ADMIN_PASSWORD in .env and run this again to create the admin.')
else:
    User.objects.create_superuser(username=email.split('@')[0], email=email, password=password,
                                  role='superadmin', is_verified=True)
    print(f'Admin created: {email}. Remove ADMIN_PASSWORD from .env now.')

print('\nDone. Restart the app in cPanel > Setup Python App, then open your domain.')
