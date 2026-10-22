"""Inspect the exported video: technical facts, one frame per step, and a contact sheet to look at.

    python demo/walkthrough/validate.py en        # or: ta

Prints codec / resolution / fps / duration / audio, writes out/<lang>/frames/*.jpg and out/contact_sheet_<LANG>.jpg.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
LANG = sys.argv[1]
OUT = HERE / 'out'
VIDEO = OUT / f'SpinalCure_Walkthrough_{LANG.upper()}.mp4'

info = subprocess.run([FFMPEG, '-i', str(VIDEO)], capture_output=True, text=True).stderr
dur = re.search(r'Duration: (\d+):(\d+):([\d.]+)', info)
seconds = int(dur[1]) * 3600 + int(dur[2]) * 60 + float(dur[3])
vid = re.search(r'Video: (\w+).*?, (\d+x\d+).*?, ([\d.]+) fps', info)
aud = re.search(r'Audio: (\w+).*?, (\d+) Hz, (\w+)', info)
print(f'{VIDEO.name}: {seconds:.1f}s ({int(seconds // 60)}m{int(seconds % 60):02d}s), video {vid[1]} {vid[2]} {vid[3]} fps, '
      f'audio {aud[1]} {aud[2]} Hz {aud[3]}, {VIDEO.stat().st_size / 1e6:.1f} MB')

data = json.loads((OUT / LANG / 'events.json').read_text(encoding='utf-8'))
trim, events = data['trim'], data['events']
frames = OUT / LANG / 'checks'
frames.mkdir(exist_ok=True)
thumbs = []
for e in events:
    t = min(seconds - 0.3, (e['start'] - trim) + min(3.5, (e['end'] - e['start']) / 2))
    path = frames / f"{e['id']}.jpg"
    subprocess.run([FFMPEG, '-y', '-ss', f'{t:.2f}', '-i', str(VIDEO), '-frames:v', '1', '-q:v', '3', str(path)],
                   capture_output=True)
    thumbs.append((e['id'], Image.open(path)))
cols, tw = 4, 480
th = int(tw * 9 / 16)
rows = (len(thumbs) + cols - 1) // cols
sheet = Image.new('RGB', (cols * tw, rows * (th + 22)), (20, 24, 28))
d = ImageDraw.Draw(sheet)
for i, (sid, im) in enumerate(thumbs):
    x, y = (i % cols) * tw, (i // cols) * (th + 22)
    sheet.paste(im.resize((tw, th)), (x, y + 22))
    d.text((x + 6, y + 4), f'{i + 1}. {sid}', fill=(110, 231, 168))
sheet.save(OUT / f'contact_sheet_{LANG.upper()}.jpg', quality=88)
print('contact sheet:', OUT / f'contact_sheet_{LANG.upper()}.jpg')
