"""
Unicode fonts for ReportLab PDFs (English, Tamil, Hindi, Arabic and the ₹ sign).

ReportLab has no font fallback, so `uni()` wraps each Tamil / Devanagari / Arabic run
in a <font> tag for the matching Noto font. Complex-script shaping (vowel signs,
Arabic joining) needs the `uharfbuzz` package, which ReportLab uses when present.
Fonts are bundled in static/fonts (SIL Open Font License).
"""
import re
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings

FONT_DIR = Path(settings.BASE_DIR) / 'static' / 'fonts'
BASE, BOLD = 'NotoSans', 'NotoSans-Bold'
_SCRIPTS = [
    ('Tamil', re.compile(r'[஀-௿]+')),
    ('Devanagari', re.compile(r'[ऀ-ॿ]+')),
    ('Arabic', re.compile(r'[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]+')),
]
_FILES = {
    'NotoSans': 'NotoSans', 'Tamil': 'NotoSansTamil', 'Devanagari': 'NotoSansDevanagari', 'Arabic': 'NotoNaskhArabic',
}


@lru_cache(maxsize=1)
def register():
    """Register fonts once; returns (regular, bold) names to use in styles."""
    from reportlab import rl_config
    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    try:
        import uharfbuzz  # noqa: F401
        rl_config.shapedFontGlob = ['Noto*']  # turn on HarfBuzz shaping for our fonts
    except ImportError:
        pass
    for key, stem in _FILES.items():
        regular = BASE if key == 'NotoSans' else f'Noto{key}'
        bold = BOLD if key == 'NotoSans' else f'Noto{key}-Bold'
        pdfmetrics.registerFont(TTFont(regular, str(FONT_DIR / f'{stem}-Regular.ttf')))
        pdfmetrics.registerFont(TTFont(bold, str(FONT_DIR / f'{stem}-Bold.ttf')))
        addMapping(regular, 0, 0, regular)
        addMapping(regular, 1, 0, bold)
        addMapping(regular, 0, 1, regular)
        addMapping(regular, 1, 1, bold)
    return BASE, BOLD


def uni(text):
    """Escape user text for a Paragraph and route non-Latin runs to the right font."""
    register()
    out = escape(str(text or ''))
    for script, rx in _SCRIPTS:
        # Hair spaces around each run: ReportLab mis-renders text glued to a shaped run in the same word.
        out = rx.sub(lambda m, s=script: f'\u200a<font name="Noto{s}">{m.group(0)}</font>\u200a', out)
    return re.sub(r'(^|\s)\u200a|\u200a(?=\s|$)', r'\1', out)  # drop hair spaces next to real spaces
