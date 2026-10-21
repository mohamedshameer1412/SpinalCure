"""Replace dummy/demo content with the real Spinal Cure (Arumbakkam) content collected on 2026-10-19 from:
  Google Maps listing (address, hours, photos, reviews), the clinic's signboard photo (doctor credentials, services),
  YouTube @SpinalCure (Shorts + videos) and Instagram @spinalcure_chennai (reels).
Idempotent. Run from project root:  python scripts/seed_real_data.py     (dev database only)
Back up first:  python manage.py dumpdata <apps> -o tmp/backup.json
"""
import html
import json
import os
import re
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "spinalcure.settings")
os.environ.setdefault("DJANGO_ENV", "development")
if os.environ["DJANGO_ENV"].lower() == "production":
    sys.exit("Refusing to run against DJANGO_ENV=production")

import django

django.setup()

from django.contrib.auth import get_user_model

from accounts.models import StaffProfile
from appointments.models import Appointment, DoctorAvailability, TimeOff
from clinic.blog_models import BlogPost, BlogTag
from clinic.models import (ClinicAboutImage, ClinicProfile, ClinicTestimonial, HeroCarouselImage, Practitioner,
                           ProblemCategory, TestimonialVideo, Translation)
from events.models import Event, EventFeedback
from notifications.models import Notification
from patients.models import Patient, PatientReview
from payments.models import Expense

User = get_user_model()
DATA = ROOT / "scripts" / "data"
today = date.today()

# ── 1. Remove dummy data ────────────────────────────────────────────────────────────────────────
removed = {}
def gone(label, qs):
    n = qs.count()
    qs.delete()
    removed[label] = n

gone("sample testimonials", ClinicTestimonial.objects.filter(source="internal"))
gone("sample videos", TestimonialVideo.objects.filter(title__startswith="[Sample]"))
gone("sample blog posts", BlogPost.objects.filter(title__in=[
    "How acupuncture helps chronic back pain", "5 desk habits that ruin your spine", "Sciatica: when to see a specialist"]))
gone("sample blog tags", BlogTag.objects.filter(posts__isnull=True))
gone("sample expenses", Expense.objects.filter(title__in=[
    "Clinic rent", "Reception salary", "Acupuncture needles (box)", "Electricity bill", "Instagram ads", "Couch repair",
    "Water can refills", "Signboard lighting"]))
gone("sample holiday", TimeOff.objects.filter(practitioner__isnull=True, reason="Public holiday"))
gone("sample notifications", Notification.objects.filter(title__in=[
    "New appointment booked", "Payment received", "Outstanding payment"], body__in=[
    "A patient booked tomorrow 6:00 pm.", "₹800 received for a session.", "2 invoices are unpaid for over 7 days."]))
gone("sample event feedback", EventFeedback.objects.filter(comment="Very informative session. The tips on posture were practical."))
gone("fake specialists", Practitioner.objects.filter(name__in=["Dr. Suresh Kumar", "Meenakshi Rao"]))
# patient names are encrypted in the database, so they cannot be filtered in SQL
fake_reviews = [r.pk for r in PatientReview.objects.select_related("patient") if r.patient.name in ("Deepa Iyer", "Anjali Krishna")]
gone("fake patient reviews", PatientReview.objects.filter(pk__in=fake_reviews))
test_patients = [p.pk for p in Patient.objects.all() if p.name in ("Test Dummy", "Test Patient AJAX", "Test Patient AJAX 3")]
gone("test patients", Patient.objects.filter(pk__in=test_patients))
gone("test events", Event.objects.filter(title__in=["Test Event Script", "camp"]))

# ── 2. Clinic profile (Google Maps + signboard + YouTube description) ───────────────────────────
clinic = ClinicProfile.objects.first() or ClinicProfile(name="Spinal Cure")
clinic.name = "Spinal Cure"
clinic.tagline = "Advanced Holistic Spine & Pain Care"
clinic.address = ("No: 194/4, 1st Floor, JN Salai, 100ft Main Rd, near Aladipattiyaan Karupatti Coffee, "
                  "Sri Sakthi Nagar, Arumbakkam, Chennai, Tamil Nadu 600106")
clinic.phone = "+91 81480 38363, +91 90876 28476"
clinic.instagram = "https://www.instagram.com/spinalcure_chennai/"
clinic.youtube = "https://www.youtube.com/@SpinalCure"
clinic.working_hours = "Mon, Tue, Wed, Thu, Sat: 5:30 pm – 8:30 pm\nFri: 10:00 am – 1:00 pm\nSun: Closed"
clinic.hero_title = "No Surgery. No Medicine. No Diet."
clinic.hero_subtitle = ("Neck & back pain special care centre in Arumbakkam, Chennai. Specialists in classical acupuncture "
                        "science for back, neck, sciatica and joint disorders, disc and nerve conditions: drug-free, "
                        "finding the root cause of your pain.")
clinic.about = ("Spinal Cure is a Neck & Back Pain Special Care Center in Arumbakkam, Chennai, led by Dr. R. Basheer Basha, "
                "a specialist in Classical Acupuncture Science. We treat neck pain, low back pain, knee pain, sciatica and "
                "disc bulges by finding the root cause of the pain and giving natural, drug-free care: no surgery, no "
                "medicine and no diet restrictions. Our focus areas are acupuncture and natural pain relief, spine and "
                "posture care, and myofascial and muscle pain management. Rated 5.0 on Google by 113 patients.")
clinic.about_title = "Natural, drug-free relief for <span class=\"text-green-600\">spine and pain</span>"
clinic.about_label = "About Spinal Cure"
clinic.about_quote = "Without Surgery, Without Medicine and Without Diet."
clinic.about_stat1_number, clinic.about_stat1_label = "5.0", "Google rating (113 reviews)"
clinic.about_stat2_number, clinic.about_stat2_label = "190+", "Patient & education videos"
clinic.footer_text = "Neck & Back Pain Special Care Center. Specialist in Classical Acupuncture Science."
clinic.map_iframe_url = (
    '<iframe src="https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3886.4971030838055!2d80.20637351081818!3d13.067650912711674'
    '!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x3a5267aee2e99775%3A0x762300885f10b7d6!2sSpinal%20Cure!5e0!3m2!1sen!2sin'
    '!4v1792368180330!5m2!1sen!2sin" width="600" height="450" style="border:0;" allowfullscreen="" loading="lazy" '
    'referrerpolicy="strict-origin-when-cross-origin"></iframe>')
clinic.save()

# Services: the conditions listed on the clinic's signboard
SERVICES = [
    ("Neck Pain & Cervical Problems", "Cervical neck pain, C1 to C8 disc issues, stiff neck and spondylitis, shoulder pain, thyroid and vertigo.", "bi-activity"),
    ("Back Pain, Disc & Sciatica", "L1 to L5 disc bulge, herniated disc, sciatica and disc prolapse, knee, leg and heel pain.", "bi-heart-pulse"),
    ("Headache, Migraine & Sleep", "Migraine, insomnia and depression, asthma and sinuses, tonsillitis issues.", "bi-flower1"),
    ("Women's Health & Fertility", "Menstrual disorders and PCOD, impotence and infertility, rheumatoid arthritis and paralysis, neurology issues and varicose veins.", "bi-bandaid"),
    ("Digestive, Skin & Hair", "Acidity and gastro disorders, piles and haemorrhoids, gallbladder stone, hair fall and skin allergy.", "bi-capsule"),
]
clinic.services.all().delete()
for i, (t, d, ic) in enumerate(SERVICES):
    clinic.services.create(title=t, description=d, icon=ic, order=i)

# Images: Google photos kept = the shop front board and the building. Removed: festival poster, patient photo, phone screenshot.
for name in ("spinalcure_2.jpg", "spinalcure_3.jpg", "spinalcure_5.jpg"):
    ClinicAboutImage.objects.filter(image__endswith=name).delete()
    HeroCarouselImage.objects.filter(image__endswith=name).delete()
for i, name in enumerate(("spinalcure_1.jpg", "spinalcure_4.jpg")):
    path = f"google_photos/{name}"
    if (ROOT / "media" / path).exists():
        HeroCarouselImage.objects.get_or_create(clinic=clinic, image=path, defaults={"order": i})
        ClinicAboutImage.objects.get_or_create(clinic=clinic, image=path, defaults={"order": i})

# ── 3. The doctor (credentials from the signboard) ──────────────────────────────────────────────
doc = Practitioner.objects.filter(name__icontains="Basheer").first() or Practitioner(name="R. Basheer Basha")
doc.name, doc.title = "R. Basheer Basha", "Dr."
doc.designation_tag = "Chief Acupuncture Doctor"
doc.specialization = "Specialist in Classical Acupuncture Science"
doc.qualifications = ("B.Sc., Master Diploma (Acu), Master Diploma in Classical (Acu), Doctor of Medicine in (Acu), "
                      "Colombo University, Sri Lanka. General Secretary, CASMA (Classical Acupuncture Science Medical Association).")
doc.bio = ("Dr. R. Basheer Basha is a specialist in Classical Acupuncture Science and the founder of Spinal Cure, Arumbakkam. "
           "He treats neck pain, low back pain, disc bulge, sciatica, knee and joint pain and many other conditions by finding "
           "the root cause of the pain and giving natural, drug-free care: no surgery, no medicine and no diet restrictions. "
           "He also teaches classical acupuncture to students at the Spinal Cure academy.")
doc.experience_years = 0
doc.youtube_url, doc.instagram = clinic.youtube, clinic.instagram
doc.phone = ""
doc.is_chief = True
doc.photo = "practitioners/basheer_basha.jpg"
doc.is_active = True
doc.save()

# ── 4. Problems ─────────────────────────────────────────────────────────────────────────────────
NEW_PROBLEMS = [("Hip Pain", "hip joint"), ("Joint Pain", "finger, hand, wrist, elbow, heel"), ("Digestive Issues", "constipation, gastro, acidity, piles"),
                ("Diabetes", "sugar"), ("Insomnia & Depression", "sleep, stress"), ("Asthma & Sinus", "breathing, tonsillitis"),
                ("Thyroid & Vertigo", "dizziness"), ("Women's Health & Fertility", "periods, pcod, infertility"),
                ("Skin & Hair", "hair fall, allergy")]
for n, kw in NEW_PROBLEMS:
    ProblemCategory.objects.get_or_create(name=n, defaults={"keywords": kw, "order": ProblemCategory.objects.count()})
prob = {p.name: p for p in ProblemCategory.objects.all()}

# ── 5. Google reviews (the 3 reviews Google shows without signing in) ───────────────────────────
GOOGLE_PROBLEM = {"banu arjunan": "Swelling & Lumps", "Kalaivani Nagarajan": "Leg Pain & Circulation", "Viji Sridar": "Sciatica",
                  "PITCHIAH S.": "Knee Pain"}
reviews_file = DATA / "google_reviews.json"
for i, r in enumerate(json.loads(reviews_file.read_text(encoding="utf-8")) if reviews_file.exists() else []):
    ClinicTestimonial.objects.update_or_create(
        clinic=clinic, patient_name=r["name"], source="google",
        defaults=dict(rating=r.get("rating", 5), review_text=r["text"], owner_reply=r.get("owner") or "", posted_label=r.get("when", ""),
                      is_published=True, display_order=i,
                      source_url="https://www.google.com/maps/place/Spinal+Cure/@13.0676457,80.2089538,17z",
                      # only the hand-checked mapping is forced; problems staff (or the import) tagged are kept
                      **({"problem": prob.get(GOOGLE_PROBLEM[r["name"]])} if r["name"] in GOOGLE_PROBLEM else {})))

# ── 6. Videos: YouTube Shorts/videos + Instagram reels ──────────────────────────────────────────
KEYWORDS = [  # first match wins; applied to title + first line of the description
    (r"sciatic", "Sciatica"), (r"disc|disk", "Slip Disc"), (r"neck", "Neck Pain"), (r"knee", "Knee Pain"),
    (r"shoulder", "Frozen Shoulder"), (r"migraine|headache", "Migraine & Headache"), (r"hip", "Hip Pain"),
    (r"finger|hand|heel|plug", "Joint Pain"), (r"constipation|gall|bowel", "Digestive Issues"), (r"diabet", "Diabetes"),
    (r"low back|lower back|back pain|back pani|spinal", "Back Pain"),
]
PICK = re.compile(r"happy patient|patient feedback|real results|pain-free|neck to legs|disc bu|sciatica|back pain|low back|"
                  r"neck|knee|migraine|constipation|diabetes|natural solution|relief|spinal testimonial", re.I)
SKIP = re.compile(r"graduat|certificate|certified|academy|workshop|course|student|studying|hegde|organ clock|noble|upgraded", re.I)
def clean(s):
    s = html.unescape(s).strip()
    return s[:1].upper() + s[1:]
def problem_for(text):
    for rx, name in KEYWORDS:
        if re.search(rx, text, re.I):
            return prob.get(name)
    return None

shorts = json.loads((DATA / "youtube_shorts.json").read_text(encoding="utf-8")) if (DATA / "youtube_shorts.json").exists() else []
videos = []
for x in shorts:
    title = clean(x["title"])
    head = x.get("desc", "").split("\n\nGet Free")[0]
    if not PICK.search(title + " " + head) or SKIP.search(title):
        continue
    when = datetime.fromisoformat(x["date"]) if x.get("date") else None
    if re.fullmatch(r"happy patients?( of classical acupuncture treatment)?( \|.*)?", title, re.I) and when:
        title = f"Happy patient story · {when:%b %Y}"
    videos.append((f"https://www.youtube.com/shorts/{x['id']}", title, problem_for(title + " " + head), when))
LONG = [("RgOzzCZJJJg", "Happy patients of classical acupuncture treatment"), ("poglfaTSo1Y", "Happy patients of classical acupuncture treatment (2)"),
        ("6VvcItQ-ePE", "Acupuncture treatment for disc bulge"), ("eRTVpFPqhMc", "Ease stiff neck pain naturally"),
        ("2AqraNjGF4g", "Happy patient: sciatica and back pain relief"), ("qt-rT0vPl8g", "Happy patient: shoulder and back pain relief"),
        ("ncwQRPta0YQ", "Happy patient: lower back pain relief"), ("VAsCIN7qtoY", "Happy patient: hip joint relief"),
        ("F-_0nT4c68M", "Happy patient: finger pain relief"), ("0IgdXX2ZiFo", "Happy patient: pain relief"),
        ("aquh7GjXJFU", "Happy patient: hand pain relief"), ("MT7Jo-HKU6U", "Low back pain explained"),
        ("gLBkcNmF7iU", "Happy patients"), ("g_BAFJHYa7E", "Happy patients (2)"), ("OFOd29m8BYo", "Happy patients (3)")]
for vid, title in LONG:
    videos.append((f"https://www.youtube.com/watch?v={vid}", title, problem_for(title), None))
INSTAGRAM_REELS = ["DeJH6Avz3cw", "Dd6l3HINSfP", "Dd1InGHTflU", "DdoODNczLCz", "DdjQ0W9zDVD", "DdeDFzPTgIm",
                   "DdY-ULlTcG6", "DdTjxyxtTtJ", "Dc1Advvz2Ng", "Dcv56Y9T-wW", "DcVYHQPT589", "DcIrx0FT9rI"]
for i, rid in enumerate(INSTAGRAM_REELS, 1):
    videos.append((f"https://www.instagram.com/reel/{rid}/", f"Spinal Cure on Instagram · reel {i}", None, None))

videos.sort(key=lambda v: (v[3] is None, -(v[3].timestamp() if v[3] else 0)))   # newest YouTube first, then the rest
for order, (url, title, problem, _when) in enumerate(videos):
    TestimonialVideo.objects.update_or_create(url=url, defaults=dict(title=title[:200], problem=problem, display_order=order, is_published=True))

# ── 7. Staff profiles for the demo logins (so My ID card works for every demo user) ────────────
for username, desig, dept in [("admin", "Super Administrator", "Administration"), ("owner", "Owner", "Management"),
                              ("doctor", "Chief Doctor", "Clinical"), ("reception", "Receptionist", "Front Desk"),
                              ("staff1", "Therapy Assistant", "Clinical"), ("clinicadmin", "Clinic Administrator", "Administration")]:
    u = User.objects.filter(username=username).first()
    if u and not hasattr(u, "staff_profile"):
        StaffProfile.objects.create(user=u, clinic=clinic, designation=desig, department=dept,
                                    joined_on=today - timedelta(days=400), contact_email=u.email)

# ── 8. Housekeeping: translations whose record no longer exists ─────────────────────────────────
from django.apps import apps
orphans = 0
for t in Translation.objects.all():
    if not apps.get_model(t.model_label).objects.filter(pk=t.object_id).exists():
        t.delete()
        orphans += 1

print("Removed:", {k: v for k, v in removed.items() if v}, "orphan translations:", orphans)
print("Now:", {m.__name__: m.objects.count() for m in (ClinicTestimonial, TestimonialVideo, ProblemCategory, Practitioner, Patient, BlogPost)})
print("YouTube:", TestimonialVideo.objects.filter(url__contains="youtube").count(), "Instagram:", TestimonialVideo.objects.filter(url__contains="instagram").count())
