#!/usr/bin/env python
"""
Wrap user-visible template text in {% trans %} / {% blocktranslate %}.

    python scripts/i18n_wrap.py templates/ accounts/ ...      # rewrite in place
    python scripts/i18n_wrap.py --dry-run templates/foo.html  # show what would change

Handled: text nodes, text containing {{ variables }} (-> blocktranslate with %(name)s placeholders), and the
attributes title / placeholder / aria-label / alt. Never touched: <script>, <style>, <pre>, <code>, <textarea>,
HTML comments, {# #}, {% comment %}, {% verbatim %}, existing {% trans %}/{% blocktrans %}, brand names and
language names written in their own script. English output is unchanged (msgid == original text, whitespace
collapsed as HTML would).
"""
import argparse
import re
import sys
from pathlib import Path

NEVER = {'SpinalCure', 'WhatsApp', 'SMS', 'PDF', 'PNG', 'CSV', 'Excel', 'JPEG', 'WebP', 'Zoom', 'Google Meet',
         'Microsoft Teams', 'Jitsi', 'GST', 'GSTIN', 'UPI', 'English', 'தமிழ்', 'हिन्दी', 'العربية', 'Noto', 'OK',
         'Tom Select', 'Chart.js', 'HTMX', 'Alpine.js', 'Bootstrap'}
OPAQUE_OPEN = re.compile(r'<(script|style|pre|code|textarea)\b[^>]*>', re.I)
TOKEN = re.compile(r'''
    (?P<comment><!--.*?-->)
  | (?P<opaque_dj>{%\s*(?:comment|verbatim|blocktrans|blocktranslate)\b.*?%}.*?{%\s*end(?:comment|verbatim|blocktrans|blocktranslate)\s*%})
  | (?P<djcomment>{\#.*?\#})
  | (?P<djtag>{%.*?%})
  | (?P<tag><(?:[^>"']|"[^"]*"|'[^']*')*>)       # a '>' inside a quoted attribute (e.g. Alpine's =>) does not end the tag
''', re.S | re.X)
VAR = re.compile(r'{{\s*(.*?)\s*}}', re.S)
LETTERS = re.compile(r'[^\W\d_]{2,}', re.U)
ATTR = re.compile(r'''\b(title|placeholder|aria-label|alt)\s*=\s*"([^"{}<>]*)"''')
TRANS_LOADED = re.compile(r'{%\s*load\s+[^%]*\bi18n\b[^%]*%}')


def _q(text):
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _skip(core):
    stripped = VAR.sub('', core).strip()
    if not LETTERS.search(stripped):
        return True
    return stripped in NEVER or all(w in NEVER for w in stripped.split())


def _var_name(expr, used):
    base = re.sub(r'\W+', '_', expr.split('|')[0].strip().split('.')[-1]).strip('_') or 'value'
    if base[0].isdigit():
        base = 'v_' + base
    name, i = base, 2
    while name in used:
        name, i = f'{base}_{i}', i + 1
    used.add(name)
    return name


def wrap_text(text):
    """Return replacement for a text node, or None to leave as is."""
    m = re.match(r'^(\s*)(.*?)(\s*)$', text, re.S)
    lead, core, trail = m.groups()
    if not core or _skip(core):
        return None
    core = ' '.join(core.split())
    if '{{' in core:
        # Django builds the %(name)s placeholder itself from {{ name }} in the body; a literal % stays a plain %.
        used, bindings = set(), []

        def sub(match):
            expr = match.group(1)
            name = _var_name(expr, used)
            bindings.append(f'{name}={expr}')
            return '{{ ' + name + ' }}'
        body = VAR.sub(sub, core)
        if '{%' in body or '%}' in body or 'blocktrans' in body:
            return None
        return f'{lead}{{% blocktranslate trimmed with {" ".join(bindings)} %}}{body}{{% endblocktranslate %}}{trail}'
    if '{%' in core or '%}' in core:
        return None
    return f'{lead}{{% trans {_q(core)} %}}{trail}'


def wrap_attrs(tag):
    def sub(m):
        name, value = m.groups()
        v = ' '.join(value.split())
        if not v or _skip(v):
            return m.group(0)
        v = v.replace('\\', '\\\\').replace("'", "\\'")        # the literal sits inside a double-quoted attribute
        return f'{name}="{{% trans \'{v}\' %}}"'
    return ATTR.sub(sub, tag)


def transform(src):
    out, pos, opaque_until = [], 0, None
    for m in TOKEN.finditer(src):
        if m.start() < pos:
            continue
        text = src[pos:m.start()]
        out.append(text if opaque_until else (wrap_text(text) or text))
        tok = m.group(0)
        kind = m.lastgroup
        if kind == 'tag':
            om = OPAQUE_OPEN.match(tok)
            if om and not tok.endswith('/>'):
                close = re.compile(rf'</{om.group(1)}\s*>', re.I).search(src, m.end())
                end = close.end() if close else len(src)
                opening = wrap_attrs(tok) if om.group(1).lower() == 'textarea' else tok   # attributes yes, content never
                out.append(opening + src[m.end():end])
                pos = end
                continue
            tok = wrap_attrs(tok)
        out.append(tok)
        pos = m.end()
    tail = src[pos:]
    out.append(wrap_text(tail) or tail)
    result = ''.join(out)
    if result != src and not TRANS_LOADED.search(result):
        ext = re.search(r'{%\s*extends\b.*?%}\s*', result)
        load = '{% load i18n %}\n'
        result = result[:ext.end()] + load + result[ext.end():] if ext and ext.start() == 0 else load + result
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='+')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    changed = 0
    for p in a.paths:
        path = Path(p)
        for f in ([path] if path.is_file() else sorted(path.rglob('*.html'))):
            src = f.read_text(encoding='utf-8-sig')   # tolerate (and drop) a byte-order mark
            new = transform(src)
            if new != src:
                changed += 1
                if not a.dry_run:
                    f.write_text(new, encoding='utf-8')
                print(('would change ' if a.dry_run else 'wrapped ') + str(f))
    print(f'{changed} templates {"would change" if a.dry_run else "changed"}')


if __name__ == '__main__':
    main()
