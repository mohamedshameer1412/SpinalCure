#!/usr/bin/env python
"""Compile locale/*/LC_MESSAGES/django.po -> django.mo with polib (no GNU gettext required). .mo files are committed."""
import sys
from pathlib import Path

import polib

ROOT = Path(__file__).resolve().parent.parent
for po_path in sorted((ROOT / 'locale').glob('*/LC_MESSAGES/django.po')):
    po = polib.pofile(str(po_path))
    translated = [e for e in po if not e.obsolete and (e.msgstr or any(e.msgstr_plural.values()))]
    out = polib.POFile()
    out.metadata = po.metadata
    for e in translated:
        out.append(e)
    out.save_as_mofile(str(po_path.with_suffix('.mo')))
    print(f'{po_path.parent.parent.name}: {len(translated)} messages -> {po_path.with_suffix(".mo").relative_to(ROOT)}')
