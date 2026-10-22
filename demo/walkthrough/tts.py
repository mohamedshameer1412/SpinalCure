"""Generate the voice-over clips (one per step) with Microsoft neural voices through edge-tts (needs internet).

    python demo/walkthrough/tts.py en        # or: ta

Writes out/<lang>/audio/<step>.mp3 and out/<lang>/audio/durations.json (seconds), which the recorder uses so every
step lasts at least as long as its narration.
"""
import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

import edge_tts
import imageio_ffmpeg

from narration import STEPS, VOICES

HERE = Path(__file__).resolve().parent
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
RATE = {'en': '-3%', 'ta': '-8%'}


def duration(path):
    err = subprocess.run([FFMPEG, '-i', str(path)], capture_output=True, text=True).stderr
    h, m, s = re.search(r'Duration: (\d+):(\d+):([\d.]+)', err).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


async def main(lang):
    out = HERE / 'out' / lang / 'audio'
    out.mkdir(parents=True, exist_ok=True)
    durations = {}
    idx = 3 if lang == 'en' else 4
    for step in STEPS:
        sid, text = step[0], step[idx]
        path = out / f'{sid}.mp3'
        await edge_tts.Communicate(text, VOICES[lang], rate=RATE[lang]).save(str(path))
        durations[sid] = round(duration(path), 2)
        print(f'{lang} {sid:15s} {durations[sid]:5.1f}s')
    (out / 'durations.json').write_text(json.dumps(durations, indent=1), encoding='utf-8')
    print(f'total narration: {sum(durations.values()):.0f}s')


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1]))
