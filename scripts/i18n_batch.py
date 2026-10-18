#!/usr/bin/env python
"""
Translation workflow helper.

    python scripts/i18n_batch.py list [N]            # next N untranslated strings (priority order) as JSON-ish lines
    python scripts/i18n_batch.py apply batch.json    # {"msgid": ["ta", "hi", "ar"], ...}; validates placeholders
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
LANGS = ['ta', 'hi', 'ar']
PRIORITY = ['templates/base.html', 'templates/partials', 'templates/components', 'accounts', 'templates/accounts', 'notifications',
            'idcards', 'templates/appointments', 'templates/events', 'templates/payments', 'templates/analytics',
            'templates/patients', 'templates/public_base', 'templates/clinic', 'clinic/', 'templates/courses',
            'templates/exports', 'templates/emails']
PH = re.compile(r'%\(\w+\)[sd]|%[sd]|&\w+;|&#\d+;|\{\{.*?\}\}|%%')


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


def cmd_list(n):
    po = load('ta')
    todo = sorted((e for e in po if not e.obsolete and not e.msgstr and not e.msgstr_plural), key=rank)[:n]
    for e in todo:
        print(json.dumps(e.msgid, ensure_ascii=False))
    print(f'# {len(todo)} listed', file=sys.stderr)


def cmd_apply(path):
    batch = json.loads(Path(path).read_text(encoding='utf-8'))
    pos = {lang: load(lang) for lang in LANGS}
    bad, applied = [], 0
    for msgid, forms in batch.items():
        if len(forms) != 3:
            bad.append((msgid, 'needs exactly 3 translations [ta, hi, ar]')); continue
        for lang, text in zip(LANGS, forms):
            if placeholders(text) != placeholders(msgid):
                bad.append((msgid, f'{lang}: placeholders differ {placeholders(msgid)} vs {placeholders(text)}'))
                break
        else:
            for lang, text in zip(LANGS, forms):
                e = pos[lang].find(msgid)
                if e is None:
                    bad.append((msgid, f'{lang}: msgid not in catalogue')); break
                e.msgstr = text
            else:
                applied += 1
    for lang, po in pos.items():
        po.metadata['X-Translation-Status'] = 'AI-drafted; requires review by a native speaker before relying on it'
        po.save()
    print(f'applied {applied}/{len(batch)}')
    for msgid, why in bad:
        print('  REJECTED', json.dumps(msgid, ensure_ascii=False)[:80], '-', why)


def cmd_check():
    problems = 0
    for lang in LANGS:
        for e in load(lang):
            if e.obsolete or not e.msgstr:
                continue
            if placeholders(e.msgstr) != placeholders(e.msgid):
                problems += 1
                print(lang, 'placeholder mismatch:', e.msgid[:70])
    print('problems:', problems)
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'list':
        cmd_list(int(sys.argv[2]) if len(sys.argv) > 2 else 200)
    elif c == 'apply':
        cmd_apply(sys.argv[2])
    elif c == 'check':
        cmd_check()
