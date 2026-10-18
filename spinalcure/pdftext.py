"""
ReportLab cannot shape Tamil, Devanagari or Arabic: it prints the code points one by one, so conjuncts, vowel signs
and Arabic joining come out wrong. Any text containing those scripts is therefore drawn with Pillow + HarfBuzz/RAQM
(the same renderer the ID cards use, with the bundled Noto fonts) and placed into the PDF as a flowable image.
Pure Latin text keeps using ordinary selectable ReportLab paragraphs.
"""
import re
from io import BytesIO
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Flowable, Paragraph

from idcards import render

NEEDS_SHAPING = re.compile('[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿ऀ-ॿ஀-௿]')
SCALE = 4          # raster pixels per PDF point: sharp at print resolution
LEADING = 1.3


def needs_shaping(text):
    return bool(text) and bool(NEEDS_SHAPING.search(str(text)))


class ShapedText(Flowable):
    """Plain text rendered with proper complex-script shaping, wrapped to the available width."""

    def __init__(self, text, size=9, color=(0, 0, 0), bold=False, align='left', max_lines=12):
        super().__init__()
        self.text, self.size, self.color, self.bold, self.align, self.max_lines = str(text), size, tuple(color), bold, align, max_lines
        self.rtl = any(render._script(ch) == 'arabic' for ch in self.text)
        self._lines, self._w = [], 0

    def wrap(self, availWidth, availHeight):
        self._w = availWidth
        px = self.size * SCALE
        self._lines = render.wrap(self.text, px, availWidth * SCALE, self.max_lines, self.bold) or ['']
        self.width, self.height = availWidth, len(self._lines) * self.size * LEADING
        return self.width, self.height

    def _png(self):
        px = int(self.size * SCALE)
        line_h = px * LEADING
        w, h = max(1, int(self._w * SCALE)), max(1, int(len(self._lines) * line_h))
        img = Image.new('RGBA', (w, h), (255, 255, 255, 0))
        d = ImageDraw.Draw(img)
        fill = tuple(int(c) for c in self.color) + (255,)
        align = self.align
        if self.rtl and align == 'left':
            align = 'right'
        x = {'left': 0, 'right': w, 'center': w / 2}[align]
        for i, line in enumerate(self._lines):
            render.draw_text(d, x, i * line_h, line, px, fill, self.bold, align, rtl=self.rtl)
        out = BytesIO()
        img.save(out, 'PNG')
        out.seek(0)
        return out

    def draw(self):
        self.canv.drawImage(ImageReader(self._png()), 0, 0, width=self.width, height=self.height, mask='auto')


def _style_color(style):
    c = getattr(style, 'textColor', None)
    return (int(c.red * 255), int(c.green * 255), int(c.blue * 255)) if c is not None and hasattr(c, 'red') else (0, 0, 0)


def para(text, style, max_lines=12):
    """A Paragraph for Latin text (escaped, so '&' and '<' in data cannot break or inject markup), or a shaped image
    flowable when the text contains Tamil/Devanagari/Arabic."""
    text = '' if text is None else str(text)
    if needs_shaping(text):
        align = {0: 'left', 1: 'center', 2: 'right'}.get(getattr(style, 'alignment', 0), 'left')
        return ShapedText(text, style.fontSize, _style_color(style), 'Bold' in getattr(style, 'fontName', ''), align, max_lines)
    return Paragraph(escape(text), style)
