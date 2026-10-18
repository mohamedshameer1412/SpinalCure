#!/usr/bin/env python
"""
Extract translatable strings (no GNU gettext needed) and merge them into locale/<lang>/LC_MESSAGES/django.po.

    python scripts/i18n_extract.py            # extract + merge for ta, hi, ar; writes locale/django.pot too
    python scripts/i18n_extract.py --stats    # translation coverage per language

Sources: Django templates ({% trans %}, {% blocktranslate %} incl. plural/context, _("...") in tags) and Python
(gettext, gettext_lazy, gettext_noop/N_, ngettext, pgettext and `_()` with a literal). Existing translations are
kept; strings that disappeared are marked obsolete rather than deleted. Compile with scripts/i18n_compile.py.
"""
import argparse
import ast
import re
import sys
from pathlib import Path

import polib

ROOT = Path(__file__).resolve().parent.parent
LOCALE = ROOT / 'locale'
LANGS = {
    'ta': ('Tamil', 'nplurals=2; plural=(n != 1);'),
    'hi': ('Hindi', 'nplurals=2; plural=(n != 1);'),
    'ar': ('Arabic', 'nplurals=6; plural=(n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5);'),
}
SKIP_DIRS = {'migrations', 'tests', 'node_modules', '.git', 'venv', 'static', 'staticfiles', 'locale', 'scripts'}
PY_FUNCS = {'gettext', 'gettext_lazy', 'gettext_noop', 'N_', '_', 'ugettext', 'ugettext_lazy'}
PY_PLURAL = {'ngettext', 'ngettext_lazy'}
PY_CTX = {'pgettext', 'pgettext_lazy'}

STR = r'''("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')'''
RE_TRANS = re.compile(r'{%\s*(?:trans|translate)\s+' + STR + r'(.*?)%}', re.S)
RE_BLOCK = re.compile(r'{%\s*(?:blocktrans|blocktranslate)\b(.*?)%}(.*?){%\s*end(?:blocktrans|blocktranslate)\s*%}', re.S)
RE_PLURAL = re.compile(r'{%\s*plural\s*%}')
RE_UNDERSCORE = re.compile(r'(?<![\w.])_\(\s*' + STR + r'\s*\)')
RE_CTX = re.compile(r'\bcontext\s+' + STR)
RE_VAR = re.compile(r'{{\s*([\w.]+)\s*}}')
IGNORE_MSGIDS = {'', ' '}


def unq(lit):
    return ast.literal_eval(lit)


def trim(s):
    return re.sub(r'\s*\n\s*', ' ', s.strip())


class Catalog(dict):
    def add(self, msgid, where, plural=None, ctx=None, py_format=False):
        if msgid in IGNORE_MSGIDS or not msgid.strip():
            return
        key = (ctx, msgid)
        e = self.setdefault(key, {'plural': plural, 'where': [], 'fmt': False})
        if plural and not e['plural']:
            e['plural'] = plural
        e['fmt'] = e['fmt'] or py_format or bool(re.search(r'%\(\w+\)[sd]|%[sd]', msgid))
        if where not in e['where']:
            e['where'].append(where)


def line_of(text, pos):
    return text.count('\n', 0, pos) + 1


def from_template(path, cat):
    text = path.read_text(encoding='utf-8-sig')
    rel = path.relative_to(ROOT)
    for m in RE_TRANS.finditer(text):
        ctx = RE_CTX.search(m.group(2))
        cat.add(unq(m.group(1)), f'{rel}:{line_of(text, m.start())}', ctx=unq(ctx.group(1)) if ctx else None)
    for m in RE_BLOCK.finditer(text):
        opts, body = m.group(1), m.group(2)
        trimmed = 'trimmed' in opts.split()
        ctx = RE_CTX.search(opts)
        parts = RE_PLURAL.split(body)

        def conv(s):
            s = trim(s) if trimmed else s
            return RE_VAR.sub(lambda v: '%(' + v.group(1) + ')s', s.replace('%', '%%'))
        singular = conv(parts[0])
        plural = conv(parts[1]) if len(parts) > 1 else None
        cat.add(singular, f'{rel}:{line_of(text, m.start())}', plural=plural, ctx=unq(ctx.group(1)) if ctx else None, py_format='%(' in singular)
    for tag in re.finditer(r'{[{%].*?[}%]}', text, re.S):
        for u in RE_UNDERSCORE.finditer(tag.group(0)):
            cat.add(unq(u.group(1)), f'{rel}:{line_of(text, tag.start())}')


def from_python(path, cat):
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'))
    except SyntaxError:
        return
    rel = path.relative_to(ROOT)
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ''
        where = f'{rel}:{n.lineno}'
        strs = [a.value for a in n.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
        if name in PY_FUNCS and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
            cat.add(n.args[0].value, where)
        elif name in PY_PLURAL and len(n.args) >= 2 and all(isinstance(a, ast.Constant) for a in n.args[:2]):
            cat.add(n.args[0].value, where, plural=n.args[1].value)
        elif name in PY_CTX and len(n.args) >= 2 and all(isinstance(a, ast.Constant) for a in n.args[:2]):
            cat.add(n.args[1].value, where, ctx=n.args[0].value)


def collect():
    cat = Catalog()
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix == '.html':
            from_template(path, cat)
        elif path.suffix == '.py' and not path.name.startswith('test_'):
            from_python(path, cat)
    return cat


def build_pot(cat):
    pot = polib.POFile()
    pot.metadata = {'Project-Id-Version': 'SpinalCure', 'MIME-Version': '1.0', 'Content-Type': 'text/plain; charset=utf-8',
                    'Content-Transfer-Encoding': '8bit'}
    for (ctx, msgid), e in sorted(cat.items(), key=lambda kv: (kv[0][1].lower(), kv[0][0] or '')):
        pot.append(polib.POEntry(msgid=msgid, msgid_plural=e['plural'] or '', msgctxt=ctx, occurrences=[tuple(w.rsplit(':', 1)) for w in e['where'][:4]],
                                 flags=['python-format'] if e['fmt'] else []))
    return pot


def merge(lang, pot):
    name, plural_forms = LANGS[lang]
    path = LOCALE / lang / 'LC_MESSAGES' / 'django.po'
    path.parent.mkdir(parents=True, exist_ok=True)
    po = polib.pofile(str(path)) if path.exists() else polib.POFile()
    po.metadata.update({'Project-Id-Version': 'SpinalCure', 'Language': lang, 'Language-Team': name,
                        'MIME-Version': '1.0', 'Content-Type': 'text/plain; charset=utf-8',
                        'Content-Transfer-Encoding': '8bit', 'Plural-Forms': plural_forms})
    po.merge(pot)
    for e in po.obsolete_entries():
        if not e.msgstr and not any(e.msgstr_plural.values()):
            po.remove(e)                                 # nothing to preserve
    po.sort(key=lambda e: (e.msgid.lower(), e.msgctxt or ''))
    po.save(str(path))
    return po


def stats():
    for lang in LANGS:
        path = LOCALE / lang / 'LC_MESSAGES' / 'django.po'
        po = polib.pofile(str(path))
        live = [e for e in po if not e.obsolete]
        done = [e for e in live if e.msgstr or any(e.msgstr_plural.values())]
        print(f'{lang}: {len(done)}/{len(live)} translated ({100 * len(done) // max(1, len(live))}%), {len(live) - len(done)} missing')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stats', action='store_true')
    a = ap.parse_args()
    if a.stats:
        return stats()
    cat = collect()
    pot = build_pot(cat)
    LOCALE.mkdir(exist_ok=True)
    pot.save(str(LOCALE / 'django.pot'))
    print(f'{len(cat)} unique strings extracted')
    for lang in LANGS:
        po = merge(lang, pot)
        print(f'  {lang}: {len([e for e in po if not e.obsolete])} entries')


if __name__ == '__main__':
    main()
