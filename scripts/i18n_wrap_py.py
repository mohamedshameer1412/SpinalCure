#!/usr/bin/env python
"""
Make user-facing strings in Python code translatable (AST based, edits source in place).

    python scripts/i18n_wrap_py.py patients appointments ...
    python scripts/i18n_wrap_py.py --dry-run patients

Rewrites:
    messages.<level>(request, 'text')            -> messages.<level>(request, gettext('text'))
    messages.<level>(request, f'Hi {name}!')     -> messages.<level>(request, gettext('Hi %(name)s!') % {'name': name})
    SchedulingError('code', 'text') / EventError / CardError                -> second argument wrapped the same way
    {'message': 'text'} / 'detail' / 'error' in JsonResponse(...) / Response(...) payloads, same treatment.
f-string fields that use a conversion (!r) are left untouched and reported.
"""
import argparse
import ast
import re
import sys
from pathlib import Path

LEVELS = {'success', 'error', 'warning', 'info', 'debug'}
JSON_KEYS = {'message', 'detail', 'error'}
JSON_CALLS = {'JsonResponse', 'Response'}
ERROR_CALLS = {'SchedulingError', 'EventError', 'CardError'}   # service-layer errors shown to users
IMPORT_LINE = 'from django.utils.translation import gettext\n'
SKIP = re.compile(r'^[\W\d_]*$')


def _name(expr, used, i):
    if isinstance(expr, ast.Name):
        base = expr.id
    elif isinstance(expr, ast.Attribute):
        base = expr.attr
    else:
        base = f'value{i}'
    name, n = base, 2
    while name in used:
        name, n = f'{base}{n}', n + 1
    used.add(name)
    return name


def convert(node, src):
    """Return replacement source for a string-ish node, or None if it should be left alone."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if SKIP.match(node.value) or len(node.value.strip()) < 2:
            return None
        return f'gettext({ast.get_source_segment(src, node)})'
    if isinstance(node, ast.JoinedStr):
        parts, used, mapping = [], set(), []
        for i, v in enumerate(node.values):
            if isinstance(v, ast.Constant):
                parts.append(str(v.value).replace('%', '%%'))
            elif isinstance(v, ast.FormattedValue):
                if v.conversion not in (-1, None):
                    return None
                nm = _name(v.value, used, i)
                expr = ast.get_source_segment(src, v.value)
                if v.format_spec is not None:
                    spec = ''.join(str(s.value) for s in v.format_spec.values if isinstance(s, ast.Constant))
                    expr = f'format({expr}, {spec!r})'
                parts.append(f'%({nm})s')
                mapping.append(f"'{nm}': {expr}")
            else:
                return None
        msgid = ''.join(parts)
        if SKIP.match(re.sub(r'%\(\w+\)s', '', msgid)):
            return None
        call = f'gettext({msgid!r})'
        return call + (f' % {{{", ".join(mapping)}}}' if mapping else '')
    return None


def edits_for(tree, src):
    out = []

    def add(node):
        rep = convert(node, src)
        if rep:
            out.append((node, rep))

    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == 'messages' \
                    and f.attr in LEVELS and len(n.args) >= 2:
                add(n.args[1])
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ''
            if name in ERROR_CALLS and len(n.args) >= 2:
                add(n.args[1])
            if name in JSON_CALLS and n.args and isinstance(n.args[0], ast.Dict):
                for k, v in zip(n.args[0].keys, n.args[0].values):
                    if isinstance(k, ast.Constant) and k.value in JSON_KEYS:
                        add(v)
    return out


def offsets(src):
    starts, pos = [], 0
    for line in src.splitlines(keepends=True):
        starts.append(pos)
        pos += len(line.encode('utf-8'))
    return starts


def process(path, dry):
    text = path.read_text(encoding='utf-8')
    tree = ast.parse(text)
    edits = edits_for(tree, text)
    if not edits:
        return 0
    raw = text.encode('utf-8')
    starts = offsets(text)
    todo = sorted(((starts[n.lineno - 1] + n.col_offset, starts[n.end_lineno - 1] + n.end_col_offset, rep) for n, rep in edits),
                  reverse=True)
    seen = set()
    for a, b, rep in todo:
        if (a, b) in seen:
            continue
        seen.add((a, b))
        raw = raw[:a] + rep.encode('utf-8') + raw[b:]
    new = raw.decode('utf-8')
    if 'import gettext\n' not in new and not re.search(r'^from django\.utils\.translation import .*\bgettext\b(?!_)', new, re.M):
        first = re.search(r'^(?:from|import) ', new, re.M)
        new = new[:first.start()] + IMPORT_LINE + new[first.start():] if first else IMPORT_LINE + new
    ast.parse(new)                                   # never write broken code
    if not dry:
        path.write_text(new, encoding='utf-8')
    return len(todo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='+')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    total = 0
    for p in a.paths:
        path = Path(p)
        for f in ([path] if path.is_file() else sorted(path.rglob('*.py'))):
            if 'migrations' in f.parts or 'tests' in f.parts or f.name.startswith('test_'):
                continue
            n = process(f, a.dry_run)
            if n:
                print(f'{n:3d}  {f}')
                total += n
    print(f'{total} strings {"would be " if a.dry_run else ""}wrapped')


if __name__ == '__main__':
    main()
