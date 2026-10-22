"""Build a fresh, disposable demo database (spinalcure_demo) and (re)start the demo server on port 8003.

    python demo/walkthrough/prepare_demo.py            # needs the local MariaDB/MySQL running (see .env for credentials)

Run it before every recording: the walkthrough makes one booking, so a used database would refuse the same guest again.
It never touches the development database: everything uses DB_NAME=spinalcure_demo.
"""
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORT = int(os.environ.get('DEMO_PORT', '8003'))
env = dict(os.environ, DB_NAME='spinalcure_demo', DJANGO_ENV='development', PYTHONUTF8='1',
           EMAIL_HOST='127.0.0.1', EMAIL_PORT='2525', EMAIL_USE_TLS='False', EMAIL_USE_SSL='False',
           EMAIL_HOST_USER='', EMAIL_HOST_PASSWORD='')          # outgoing mail goes nowhere: the demo never emails anyone


def run(*args):
    r = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f'{args} failed:\n{r.stdout[-800:]}\n{r.stderr[-800:]}')
    return r.stdout


def sql(statement):
    mysql = os.environ.get('MYSQL_BIN', r'C:/xampp/mysql/bin/mysql.exe')
    subprocess.run([mysql, '-uroot', '-e', statement], check=True)


def kill_port():
    out = subprocess.run(['netstat', '-ano'], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if f':{PORT} ' in line and 'LISTENING' in line:
            subprocess.run(['taskkill', '/F', '/PID', line.split()[-1]], capture_output=True)


kill_port()
time.sleep(1)
sql('DROP DATABASE IF EXISTS spinalcure_demo; CREATE DATABASE spinalcure_demo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;')
run('manage.py', 'migrate', '--noinput')
run('manage.py', 'createcachetable')
run('manage.py', 'loaddata', 'deploy/content.json')
print(run('demo/walkthrough/seed_demo.py').strip().splitlines()[-1])
log = open(ROOT / 'tmp' / 'server_demo.log', 'w')
subprocess.Popen([sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{PORT}', '--noreload'], cwd=ROOT, env=env,
                 stdout=log, stderr=log, creationflags=0x00000008 | 0x00000200)   # detached, no console window
for _ in range(40):
    try:
        if urllib.request.urlopen(f'http://127.0.0.1:{PORT}/en/', timeout=3).status == 200:
            print(f'Demo server ready on http://127.0.0.1:{PORT}')
            break
    except Exception:
        time.sleep(1)
else:
    sys.exit('demo server did not start')
