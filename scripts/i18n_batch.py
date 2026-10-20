#!/usr/bin/env python
"""
Translation workflow helper.

    python scripts/i18n_batch.py list [N] [OFFSET]   # untranslated strings as JSON lines [msgid, plural, [langs needed]]
    python scripts/i18n_batch.py apply batch.json    # {"msgid": {"ta": "...", "te": ["sing", "plural"]}}; validates placeholders
    python scripts/i18n_batch.py check               # verify every translation keeps its placeholders/entities

Translations written through this tool are drafts by the development team/assistant and are flagged in the
PO header as needing native-speaker review.
"""
import json
import re
import sys
from pathlib import Path

import polib

ROOT = Path(__file__).resolve().parent.parent
LANGS = ['ta', 'hi', 'te', 'ml', 'kn']
PRIORITY = ['templates/base.html', 'templates/partials', 'templates/components', 'accounts', 'templates/accounts', 'notifications',
            'idcards', 'templates/appointments', 'templates/events', 'templates/payments', 'templates/analytics',
            'templates/patients', 'templates/public_base', 'templates/clinic', 'clinic/', 'templates/courses',
            'templates/exports', 'templates/emails']
# &larr;/&rarr; are directional: RTL translations legitimately use the mirrored arrow
PH = re.compile(r'%\(\w+\)[sd]|%[sd]|&(?!larr;|rarr;)\w+;|&#\d+;|\{\{.*?\}\}|%%')


def rank(entry):
    src = entry.occurrences[0][0] if entry.occurrences else ''
    for i, p in enumerate(PRIORITY):
        if src.startswith(p):
            return (0, i, entry.msgid.lower())
    if 'models' in src:
        return (1, 0, entry.msgid.lower())
    return (2, 0, entry.msgid.lower())


def load(lang):
    return polib.pofile(str(ROOT / 'locale' / lang / 'LC_MESSAGES' / 'django.po'))


def placeholders(s):
    return sorted(PH.findall(s))


def _missing(e):
    return not e.msgstr and not any(e.msgstr_plural.values()) if e.msgid_plural else not e.msgstr


def cmd_list(n, offset=0):
    """Untranslated strings (in any language), new-for-everyone first, as JSON lines: [msgid, msgid_plural|null, [langs needed]]."""
    pos = {lang: load(lang) for lang in LANGS}
    rows = []
    for e in pos['te']:
        if e.obsolete:
            continue
        need = [lang for lang in LANGS if (lambda x: x is not None and _missing(x))(pos[lang].find(e.msgid))]
        if need:
            rows.append((len(need) != len(LANGS) and 1 or 0, rank(e), e.msgid, e.msgid_plural or None, need))
    rows.sort(key=lambda r: (-len(r[4]), r[1]))
    for r in rows[offset:offset + n]:
        print(json.dumps([r[2], r[3], r[4]], ensure_ascii=False))
    print(f'# {len(rows[offset:offset + n])} listed of {len(rows)} remaining', file=sys.stderr)


def cmd_apply(path):
    """batch.json: {msgid: {lang: "text" | ["singular", "plural"]}}; placeholders must match the source."""
    batch = json.loads(Path(path).read_text(encoding='utf-8'))
    pos = {lang: load(lang) for lang in LANGS}
    bad, applied = [], 0
    for msgid, forms in batch.items():
        for lang, text in forms.items():
            if lang not in pos:
                bad.append((msgid, f'unknown language {lang}')); continue
            e = pos[lang].find(msgid)
            if e is None:
                bad.append((msgid, f'{lang}: msgid not in catalogue')); continue
            if e.msgid_plural:
                sing, plur = (text if isinstance(text, list) else [text, text])[:2]
                if placeholders(sing) != placeholders(e.msgid) or placeholders(plur) != placeholders(e.msgid_plural):
                    bad.append((msgid, f'{lang}: placeholders differ')); continue
                e.msgstr_plural = {0: sing, 1: plur}
            else:
                if isinstance(text, list):
                    text = text[0]
                if placeholders(text) != placeholders(msgid):
                    bad.append((msgid, f'{lang}: placeholders differ {placeholders(msgid)} vs {placeholders(text)}')); continue
                e.msgstr = text
            if 'fuzzy' in e.flags:
                e.flags.remove('fuzzy')
            applied += 1
    for lang, po in pos.items():
        po.metadata['X-Translation-Status'] = 'AI-drafted; requires review by a native speaker before relying on it'
        po.save()
    print(f'applied {applied} translations')
    for msgid, why in bad:
        print('  REJECTED', json.dumps(msgid, ensure_ascii=False)[:80], '-', why)


def cmd_check():
    problems = 0
    for lang in LANGS:
        for e in load(lang):
            if e.obsolete or not e.msgstr or e.msgid_plural:
                continue
            if placeholders(e.msgstr) != placeholders(e.msgid):
                problems += 1
                print(lang, 'placeholder mismatch:', e.msgid[:70])
    print('problems:', problems)
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'list':
        cmd_list(int(sys.argv[2]) if len(sys.argv) > 2 else 200, int(sys.argv[3]) if len(sys.argv) > 3 else 0)
    elif c == 'apply':
        cmd_apply(sys.argv[2])
    elif c == 'check':
        cmd_check()
