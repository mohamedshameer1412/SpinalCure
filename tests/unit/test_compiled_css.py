"""The committed Tailwind build contains the utilities the templates rely on (classes chosen in Python are not
scanned by Tailwind, and the aspect-ratio plugin once dropped aspect-video)."""
from pathlib import Path

CSS = (Path(__file__).resolve().parents[2] / 'static/css/tailwind.css').read_text()


def test_aspect_utilities_are_compiled():
    for rule in ('.aspect-video{aspect-ratio:16/9}', '.aspect-square{aspect-ratio:1/1}',
                 r'.aspect-\[9\/16\]{aspect-ratio:9/16}', r'.aspect-\[4\/5\]{aspect-ratio:4/5}'):
        assert rule in CSS, rule
