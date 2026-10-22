"""Build the upload package for cPanel: dist/spinalcure-cpanel.zip

    DJANGO_ENV=development python scripts/export_content.py   # refresh deploy/content.json + deploy/media first
    python scripts/build_release.py

Leaves out everything that must not or need not go to the server (docs, tests, dev scripts, translation sources): secrets (.env), local databases, virtualenvs,
node_modules, caches, logs, the local media folder (patients' files) and scratch work.
"""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'dist' / 'spinalcure-cpanel.zip'

# skipped wherever they appear
SKIP_ANYWHERE = {'.git', '.pytest_cache', '__pycache__', 'node_modules', 'htmlcov'}
# skipped only at the project root (static/img, deploy/media etc. must ship)
SKIP_AT_ROOT = {'.vscode', '.idea', '.playwright-mcp', '.claude', 'venv', '.venv', 'env', 'tmp', 'logs', 'media',
                'staticfiles', 'dist', 'img', 'private_media', 'tests', 'scripts', 'docs', '.github'}
# development-only files at the project root
SKIP_ROOT_FILES = {'pytest.ini', 'run_tests.sh', 'run_tests.bat', 'requirements-dev.txt', '.gitignore', '.gitattributes',
                   '.env.example', 'package.json', 'package-lock.json'}
SKIP_FILES = {'.env', 'db.sqlite3', 'pyrightconfig.json'}
SKIP_SUFFIXES = ('.pyc', '.pyo', '.log', '.sqlite3')


def wanted(rel: Path):
    parts = rel.parts
    if rel.suffix == '.md' or rel.name == 'conftest.py':                      # documentation and test setup
        return False
    if len(parts) == 1 and rel.name in SKIP_ROOT_FILES:
        return False
    if parts[:2] == ('theme', 'static_src'):                                  # CSS build sources: the compiled file ships
        return False
    if parts[0] == 'locale' and rel.suffix in ('.po', '.pot'):                # only the compiled .mo files are used
        return False
    if rel.name in SKIP_FILES or rel.name.endswith(SKIP_SUFFIXES):
        return False
    if len(parts) > 1 and parts[0] in SKIP_AT_ROOT:
        return False
    return not any(p in SKIP_ANYWHERE for p in parts[:-1])


def main():
    OUT.parent.mkdir(exist_ok=True)
    count = 0
    with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(ROOT.rglob('*')):
            if path.is_file():
                rel = path.relative_to(ROOT)
                if wanted(rel):
                    z.write(path, Path('spinalcure') / rel)
                    count += 1
        z.writestr('spinalcure/logs/.keep', '')          # Passenger and Django write logs here
        # The folder may sit inside a domain's web folder on shared hosting: nothing in it may be downloaded directly
        # (source code, .env, logs, the database export). The app itself is served by Passenger, not by this folder.
        z.writestr('spinalcure/.htaccess', '''# Written by build_release.py: this folder is an application, not a website.
<IfModule mod_authz_core.c>
    Require all denied
</IfModule>
<IfModule !mod_authz_core.c>
    Order deny,allow
    Deny from all
</IfModule>
Options -Indexes
''')
    print(f'{count} files -> {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)')


if __name__ == '__main__':
    main()
