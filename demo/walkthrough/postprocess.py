"""Turn the raw recording into the final video: H.264 1080p30, the voice-over mixed in at each step, an .srt subtitle file.

    python demo/walkthrough/postprocess.py en        # or: ta

Reads out/<lang>/raw.webm, events.json and audio/*.mp3. Writes out/SpinalCure_Walkthrough_<LANG>.mp4 and .srt.
Nothing is sped up or cut except the blank first frame before the title card appears.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

HERE = Path(__file__).resolve().parent
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
LANG = sys.argv[1]
OUT = HERE / 'out'
SRC = OUT / LANG
NAME = f'SpinalCure_Walkthrough_{LANG.upper()}'


def stamp(t):
    ms = int(round(t * 1000))
    return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}'


def main():
    data = json.loads((SRC / 'events.json').read_text(encoding='utf-8'))
    trim, total, events = data['trim'], data['total'], data['events']
    from PIL import Image
    frames = [(t, n) for t, n in json.loads((SRC / 'frames.json').read_text(encoding='utf-8'))
              if Image.open(SRC / 'frames' / n).size == (1920, 1080)]          # skip any odd-sized frame from before the viewport settled
    # subtitles: each caption lasts from its start until the next one begins
    lines = []
    for i, e in enumerate(events):
        start = e['start'] - trim
        end = (events[i + 1]['start'] - trim) if i + 1 < len(events) else (e['end'] - trim)
        lines.append(f"{i + 1}\n{stamp(start)} --> {stamp(end - 0.05)}\n{e['text']}\n")
    (OUT / f'{NAME}.srt').write_text('\n'.join(lines), encoding='utf-8')

    # picture: every frame is shown from the moment Chrome painted it until the next one (variable timing, exact);
    # the blank first frame before the title card is skipped
    first = max(i for i, (t, _n) in enumerate(frames) if t <= trim) if any(t <= trim for t, _n in frames) else 0
    seq = frames[first:]
    listing = SRC / 'frames.txt'
    with open(listing, 'w', encoding='utf-8') as fh:
        for i, (t, name) in enumerate(seq):
            begin = max(t, trim)
            end = seq[i + 1][0] if i + 1 < len(seq) else total
            fh.write(f"file 'frames/{name}'\nduration {max(end - begin, 0.001):.4f}\n")
        fh.write(f"file 'frames/{seq[-1][1]}'\n")
    video_len = total - trim

    cmd = [FFMPEG, '-y', '-f', 'concat', '-safe', '0', '-i', str(listing)]
    for e in events:
        cmd += ['-i', str(SRC / 'audio' / f"{e['id']}.mp3")]
    delays = []
    for i, e in enumerate(events):
        ms = max(0, int(round((e['start'] - trim + 0.15) * 1000)))
        delays.append(f'[{i + 1}:a]adelay={ms}|{ms}[a{i}]')
    mix = ''.join(f'[a{i}]' for i in range(len(events))) + f'amix=inputs={len(events)}:normalize=0:dropout_transition=0[aout]'
    cmd += ['-filter_complex', f'[0:v]fps=30,scale=1920:1080:flags=lanczos,format=yuv420p[vout];' + ';'.join(delays) + ';' + mix,
            '-map', '[vout]', '-map', '[aout]', '-t', f'{video_len:.2f}',
            '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-profile:v', 'high', '-movflags', '+faststart',
            '-c:a', 'aac', '-b:a', '160k', '-ar', '44100', '-ac', '2', str(OUT / f'{NAME}.mp4')]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr[-2000:])
    print(f'wrote {OUT / (NAME + ".mp4")}')


if __name__ == '__main__':
    main()
