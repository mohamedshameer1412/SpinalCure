"""Build the upload package for cPanel: dist/spinalcure-cpanel.zip

    DJANGO_ENV=development python scripts/export_content.py   # refresh deploy/content.json + deploy/media first
    python scripts/build_release.py

Leaves out everything that must not or need not go to the server: secrets (.env), local databases, virtualenvs,
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
                'staticfiles', 'dist', 'img', 'private_media'}
SKIP_FILES = {'.env', 'db.sqlite3', 'pyrightconfig.json'}
SKIP_SUFFIXES = ('.pyc', '.pyo', '.log', '.sqlite3')


def wanted(rel: Path):
    parts = rel.parts
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
    print(f'{count} files -> {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)')


if __name__ == '__main__':
    main()
