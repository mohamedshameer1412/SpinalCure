# Walkthrough report

## What was produced
| File | Language | Length | Format |
|---|---|---|---|
| `out/SpinalCure_Walkthrough_EN.mp4` | English interface, captions, voice | 5 min 32 s | H.264 1920×1080, 30 fps, AAC stereo, 35.6 MB |
| `out/SpinalCure_Walkthrough_TA.mp4` | Tamil interface, captions, voice | 7 min 12 s | H.264 1920×1080, 30 fps, AAC stereo, 41.1 MB |
| `out/SpinalCure_Walkthrough_EN.srt`, `_TA.srt` | subtitles (also burned into the picture) | | SubRip |
| `out/contact_sheet_EN.jpg`, `_TA.jpg` | one frame per step, for review | | JPEG |

Source: `script.md` (step table), `narration.py` (captions + voice text, both languages), `tts.py` (voice clips),
`record.py` (recorder), `postprocess.py` (final encode), `validate.py` (checks), `prepare_demo.py` and `seed_demo.py`
(disposable demo database).

## What the videos show (27 steps each)
Public website (home, About with the logo beside the text, treatments, doctor, patient stories with "Show more", online
booking from typing to confirmation, six-language switch, FAQ) then the back office (sign-in, dashboard, appointments including
the booking just made, weekly availability, patients, patient record, payments, payments report, courses and batches with a
clickable batch card, attendance and certificates, students, a student's ID card, staff ID cards, Reels and Shorts, Clinic Setup).

## Verified
- Every step completed in a real Chrome window on a disposable database (`spinalcure_demo`) with synthetic patients and
  students: **27/27 steps passed in both languages** (`out/<lang>/events.json`).
- The booking made on camera appears in the staff appointment list a few steps later, with the guest's name.
- Technical checks (`validate.py`): H.264 High, 1920×1080, 30 fps, AAC 44.1 kHz stereo, plays from the first frame.
- Contact sheets inspected for every step: caption, page and cursor agree in both videos.

## Fixed while preparing the walkthrough
- Online (guest) bookings were listed as "Patient record not found"; they now show the guest's name, phone and an
  "Online booking" tag (all six languages).
- The first two attempts to record were rejected by the checks: Playwright's built-in video ran several seconds behind
  the clock, which would have put the voice ahead of the picture. The recorder now takes Chrome's own screencast frames with
  their true timestamps, and the voice is placed against those.

## Not shown / limitations
See `script.md`, Part 3. In short: real emails/SMS are disabled in the demo, online payment, YouTube/Google-review sync,
fee instalments, study materials, certificate e-mailing and the student sign-in link were not recorded. Tamil text was
written for this walkthrough and has not been proofread by a native speaker. Screen frames are variable-rate and re-timed
to 30 fps.

## Changes to the project
`templates/appointments/partials/appointment_list_partial.html` (guest name) and the matching translations. Everything under
`demo/walkthrough/` is new. `scripts/build_release.py` now leaves `demo/` out of the cPanel zip.

## Cleanup
The demo server (port 8003) was stopped, the `spinalcure_demo` database dropped, and the raw frame folders (about 2 GB)
deleted. Nothing was changed in the development database. To record again: `python demo/walkthrough/prepare_demo.py`, then
`tts.py`, `record.py`, `postprocess.py`, `validate.py` for each language.
