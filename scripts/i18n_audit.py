#!/usr/bin/env python
"""
Audit templates for user-visible text that is NOT wrapped for translation.

    python scripts/i18n_audit.py            # summary per template
    python scripts/i18n_audit.py -v         # also print every offending string
    python scripts/i18n_audit.py --fail-on templates/idcards   # exit 1 if any string is found under these paths

It looks at text nodes and the attributes title / placeholder / aria-label / alt / value (on buttons).
Strings made only of variables, numbers or symbols are ignored. This reports *template* text only; strings
in Python code, JavaScript literals and database content are outside its scope.
"""
import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAG_BLOCKS = [
    re.compile(r'{%\s*(?:blocktrans|blocktranslate)\b.*?%}.*?{%\s*end(?:blocktrans|blocktranslate)\s*%}', re.S),
    re.compile(r'{#.*?#}', re.S), re.compile(r'{%\s*comment\b.*?%}.*?{%\s*endcomment\s*%}', re.S),
    re.compile(r'{%\s*verbatim\s*%}.*?{%\s*endverbatim\s*%}', re.S),
]
TRANS_TAG = re.compile(r'{%\s*(?:trans|translate)\b.*?%}', re.S)
DJANGO_TAG = re.compile(r'{%.*?%}', re.S)
DJANGO_VAR = re.compile(r'{{.*?}}', re.S)
LETTERS = re.compile(r'[^\W\d_]{2,}', re.U)
ATTRS = ('title', 'placeholder', 'aria-label', 'alt')
SKIP_TAGS = {'script', 'style', 'code', 'pre', 'title'}


class Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.found = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in ('br', 'img', 'input', 'meta', 'link', 'hr'):
            self.stack.append(tag)
        for name, value in attrs:
            if value and (name in ATTRS or (name == 'value' and tag in ('button', 'input') and dict(attrs).get('type') in ('submit', 'button'))):
                self._check(value, f'@{name}')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        while self.stack and self.stack.pop() != tag:
            pass

    def handle_data(self, data):
        if not any(t in SKIP_TAGS for t in self.stack):
            self._check(data, 'text')

    def _check(self, text, kind):
        t = DJANGO_VAR.sub(' ', text)
        t = re.sub(r'\bTRANSLATED\b', ' ', t)          # placeholder for {% trans %}/blocktrans
        t = re.sub(r'&\w+;|&#\d+;', ' ', t).strip()
        if LETTERS.search(t):
            self.found.append((kind, ' '.join(t.split())[:90]))


def audit(path):
    src = path.read_text(encoding='utf-8', errors='ignore')
    for rx in TAG_BLOCKS:
        src = rx.sub(' TRANSLATED ', src)
    src = TRANS_TAG.sub(' TRANSLATED ', src)
    src = DJANGO_TAG.sub(' ', src)
    # django vars inside attribute values must not trip the parser
    c = Collector()
    try:
        c.feed(src)
    except Exception:
        pass
    return c.found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-v', '--verbose', action='store_true')
    ap.add_argument('--fail-on', nargs='*', default=[])
    args = ap.parse_args()
    files = sorted(p for d in ('templates', 'accounts', 'clinic', 'patients', 'appointments', 'payments', 'events', 'courses',
                               'analytics', 'notifications', 'idcards', 'theme') for p in (ROOT / d).rglob('*.html') if 'node_modules' not in p.parts)
    total = 0
    rows = []
    for f in files:
        found = audit(f)
        total += len(found)
        rows.append((len(found), f.relative_to(ROOT), found))
    rows.sort(key=lambda r: (-r[0], str(r[1])))
    clean = sum(1 for n, *_ in rows if n == 0)
    for n, rel, found in rows:
        if n or args.verbose:
            print(f'{n:4d}  {rel}')
        if args.verbose:
            for kind, text in found:
                print(f'        [{kind}] {text}')
    print(f'\n{len(files)} templates, {clean} fully wrapped, {total} untranslated strings in {len(files) - clean} templates')
    bad = [(n, rel) for n, rel, _f in rows if n and any(str(rel).startswith(p) for p in args.fail_on)]
    if bad:
        print('FAIL: untranslated strings under', ', '.join(args.fail_on))
        sys.exit(1)


if __name__ == '__main__':
    main()
