# Spinal Cure: walkthrough script (English and Tamil)

Two videos are produced from one script: `SpinalCure_Walkthrough_EN.mp4` (English interface, English captions and voice) and
`SpinalCure_Walkthrough_TA.mp4` (the whole interface switched to Tamil, Tamil captions and Tamil voice). Captions are burned
into the picture and also written to `.srt` files; the caption text is exactly what the voice says.

## Part 1: Product introduction

Spinal Cure is a clinic in Arumbakkam, Chennai (Dr. R. Basheer Basha, classical acupuncture). This application is both the
clinic's public website, where a patient can read about treatments, watch patient stories and book an appointment online, and
the back office staff use every day: appointments and weekly availability, patients and payments, courses with attendance and
certificates, student and staff ID cards, and the website's own content. The site and the back office run in six languages.

The walkthrough follows one patient from the website to a confirmed booking, then shows how staff see that booking and run the
rest of the clinic. It is recorded on a **disposable demo database with made-up patients and students**; nothing real is shown.

## Part 2: Recording script

| # | Screen or route | Action | Caption (English; the Tamil text is in `narration.py`) | Verified by |
|---|---|---|---|---|
| 1 | Title card | Logo, title, five-point outline, demo-data note | Spinal Cure: clinic management and patient website… | Card shown at 1920×1080 |
| 2 | `/en/` | Hero, cursor on Book appointment | The public website opens with the clinic's promise… | `h1` visible |
| 3 | `/en/#about` | Scroll to About | The About section shows the clinic logo beside its story… | Section in view |
| 4 | `/en/#treatments` | Scroll | Visitors browse the problems the clinic treats… | Section in view |
| 5 | `/en/#doctor` | Scroll | They meet the doctor… | Section in view |
| 6 | `/en/clinic/testimonials/` | Click Patient stories, scroll, click Show more | Patient stories gather reviews and video reels… | Article count increases after Show more |
| 7 | `/en/#book` | Type name, phone, email | Booking takes under a minute… | Fields filled |
| 8 | Booking card | Open date picker, pick a Tuesday | Choosing a date shows only the free times… | Time slots appear |
| 9 | Booking card | Pick a time, type a reason, Confirm | One tap confirms the appointment… | Booking form replaced by the confirmation |
| 10 | Header language menu | Switch to the other language and back | The whole site comes in six languages… | URL language prefix changes and returns |
| 11 | `/en/clinic/faq/` | Open a question | Every answer is checked by a named doctor… | Page loads |
| 12 | `/en/accounts/login/` | Type the demo account, sign in | Staff sign in with their own account… | Redirect to the dashboard |
| 13 | Dashboard | Scroll | The dashboard summarises today's appointments… | Page loads |
| 14 | Appointments (calendar, then list) | Click through to the list | The appointment calendar shows the online booking just made… | A row for the guest who just booked is present |
| 15 | Availability | Scroll | Weekly hours are set for each doctor… | Weekly form present |
| 16 | Patients | Search "Priya" | The patient list is searchable… | Results narrow to one row |
| 17 | Patient record | Open and scroll | Each patient's record keeps details, sittings, payments… | URL is a patient page |
| 18 | Payments | Hover a row | Payments record the amount, balance and mode… | Table present |
| 19 | Payments report | View | The payments report totals… | Page loads |
| 20 | Courses → Batches → batch | Click the batch card (whole card is a link) | Courses and batches are managed here… | Registrations page opens |
| 21 | Attendance | View the matrix | Attendance is marked class by class… | Checkbox matrix present |
| 22 | Students | View the list | Every student has one profile… | Table present |
| 23 | Student profile | Open Anitha, scroll to the ID card | The student's vertical ID card is drawn automatically… | Card image present |
| 24 | ID cards → card | Open a staff card | Staff ID cards use the same design… | Card stage present |
| 25 | Reels and Shorts | Scroll | Reels and Shorts from the YouTube channel are sorted by problem… | Page loads |
| 26 | Clinic Setup | Scroll | Clinic Setup holds the profile, About text, hours… | Page loads |
| 27 | End card | Closing statement and demo-data note | Spinal Cure, Arumbakkam, Chennai… | Card shown |

## Part 3: Known limitations

- **Not shown (not demonstrated, not claimed):** online payments (Razorpay is not configured here), sending of real emails and
  SMS (outgoing mail is disabled in the demo), the YouTube and Google-review sync (they need keys and approval), course-fee
  instalments, study-material uploads, certificate e-mailing, and the student sign-in link. These exist in the code and are
  covered by automated tests, but they were not recorded.
- The confirmation after booking says an email "is on its way"; in the demo no email is actually sent.
- Seconds spent waiting for the booking request to complete (the demo server tries, and fails, to reach a mail server) are
  left in the video as they happened.
- The video is composed from Chrome's screen frames at their true timing (variable frame rate, re-timed to 30 fps). The
  encoder is the bundled ffmpeg of imageio-ffmpeg.
- Tamil voice and captions were written for this walkthrough and have not been proofread by a native speaker.
