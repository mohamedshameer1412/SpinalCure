"""Courses, batches and free health events for the public site, illustrated with the clinic's own photos.

    DJANGO_ENV=development python scripts/seed_programs.py

Idempotent by title: an existing course or event is updated only where a field is empty (staff edits win), except
images, which replace the old placeholder pictures. Fees and dates are starting values for the clinic to confirm
in Staff > Courses / Events before promoting them.
"""
import os
import sys
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'spinalcure.settings')
os.environ.setdefault('DJANGO_ENV', 'development')
import django  # noqa: E402

django.setup()
from django.core.files import File  # noqa: E402
from clinic.models import ClinicProfile, Practitioner  # noqa: E402
from courses.models import Course, CourseBatch  # noqa: E402
from events.models import Event  # noqa: E402

PHOTOS = ROOT / 'media' / 'programs'
clinic = ClinicProfile.objects.first()
doctor = Practitioner.objects.filter(is_active=True).first()
presenter = f'{doctor.title} {doctor.name}'.strip() if doctor else 'Dr. R. Basheer Basha'
venue = ' '.join((clinic.address or '').split()) if clinic else 'Spinal Cure, Arumbakkam, Chennai'
today = date.today()


def next_weekday(start, weekday, weeks=0):
    return start + timedelta(days=(weekday - start.weekday()) % 7 + 7 * weeks)


def set_image(obj, field, name):
    path = PHOTOS / name
    if not path.exists():
        return
    current = getattr(obj, field)
    if current and Path(current.name).name.startswith(Path(name).stem):
        return                                            # already ours
    with path.open('rb') as fh:
        current.save(name, File(fh), save=False)


def upsert(model, lookup, values, image=None):
    obj = model.objects.filter(**lookup).first()
    created = obj is None
    if created:
        obj = model(**lookup)
    for k, v in values.items():
        if created or not getattr(obj, k):
            setattr(obj, k, v)
    if image:
        set_image(obj, 'image', image)
    obj.save()
    return obj, created


COURSES = [
    ('Basic Acupuncture Certification', 'needle-insertion.jpg', {
        'short_description': 'A 3-month foundation course in classical acupuncture: points, needling and patient care.',
        'description': 'A practical introduction to classical acupuncture for beginners and health workers. You learn '
                       'how the body\'s channels and points are located, safe needling with sterile single-use '
                       'needles, and how a sitting is planned around the root cause of a patient\'s pain. Classes '
                       'combine theory with supervised practice at the clinic.',
        'outcomes': 'Locate the main acupuncture points\nNeedle safely with sterile, single-use needles\n'
                    'Take a patient history and plan a sitting\nKnow when to refer a patient to a hospital',
        'course_content': 'History and principles of classical acupuncture\nChannels and point location\n'
                          'Hygiene, safety and needling technique\nCommon pain conditions: back, neck, knee, shoulder\n'
                          'Supervised clinical practice',
        'platform': Course.PLATFORM_OFFLINE, 'fees': Decimal('25000'), 'duration': '3 months',
    }),
    ('Acupressure for Everyday Pain Relief', 'needle-wrist.jpg', {
        'short_description': 'A one-day, hands-on workshop: simple pressure points you can use at home for neck, '
                             'back and headache.',
        'description': 'No needles: a friendly one-day workshop for anyone who wants simple self-care. Learn a small '
                       'set of pressure points and how to use them safely for everyday neck and back tension, '
                       'headache and sleep, and when to see a doctor instead.',
        'outcomes': 'Find and press key points safely\nA 10-minute daily self-care routine\n'
                    'Warning signs that need a doctor',
        'course_content': 'What acupressure is (and is not)\nPoints for neck, shoulder and back tension\n'
                          'Points for headache and sleep\nPractice in pairs',
        'platform': Course.PLATFORM_OFFLINE, 'fees': Decimal('1500'), 'duration': '1 day',
    }),
    ('Advanced Classical Acupuncture: Spine and Joints', 'classical-text.jpg', {
        'short_description': 'For practitioners: assessment and treatment planning for spine, disc and joint pain.',
        'description': 'An advanced course for practitioners who have completed a foundation course. It focuses on '
                       'examining spine and joint problems, reading scan reports with the patient, and planning a '
                       'course of sittings for back pain, disc bulge, sciatica, neck, shoulder and knee pain.',
        'outcomes': 'Assess spine and joint pain systematically\nPlan and review a course of sittings\n'
                    'Explain the plan clearly to patients',
        'course_content': 'Examination of the spine and joints\nDisc bulge and sciatica\nNeck and shoulder\n'
                          'Knee and hip\nCase discussions from the clinic',
        'platform': Course.PLATFORM_HYBRID, 'fees': Decimal('45000'), 'duration': '6 months',
    }),
]

for title, image, values in COURSES:
    course, created = upsert(Course, {'title': title}, {**values, 'clinic': clinic, 'is_published': True}, image)
    if not course.batches.filter(start_date__gte=today).exists():
        start = next_weekday(today, 0, 3)                  # a Monday about three weeks out
        CourseBatch.objects.create(course=course, name=f'{start:%B %Y} batch', start_date=start,
                                   schedule_details='Weekdays, 10:00 am – 1:00 pm at the clinic',
                                   max_participants=12, is_active=True, is_published=True)
    print(('created ' if created else 'updated ') + title)

EVENTS = [
    ('Free Back and Neck Pain Check-up Camp', 'spine-pain.jpg', {
        'event_type': 'camp', 'is_online': False, 'venue': venue,
        'date': next_weekday(today, 5, 2), 'start_time': time(10, 0), 'end_time': time(13, 0),
        'description': 'A free morning at the clinic for anyone living with back or neck pain. Meet the doctor, have '
                       'your posture and movement checked, and ask your questions. Bring any scans or reports you '
                       'have. Seats are limited, so please register.',
        'max_participants': 40,
    }),
    ('Online Talk: Sciatica, Causes and Natural Relief', 'needles-classical-coin.jpg', {
        'event_type': 'webinar', 'is_online': True, 'meeting_provider': 'Google Meet',
        'date': next_weekday(today, 6, 3), 'start_time': time(18, 0), 'end_time': time(19, 0),
        'description': 'A one-hour online talk on sciatica: why pain travels down the leg, what makes it worse, '
                       'simple daily habits that help, and how classical acupuncture approaches it. Questions are '
                       'welcome at the end. The joining link is emailed after you register.',
        'max_participants': 200, 'access_instructions': 'The joining link is sent by email the day before the talk.',
    }),
    ('Posture Workshop for Desk Workers', 'candle-acupuncture.jpg', {
        'event_type': 'workshop', 'is_online': False, 'venue': venue,
        'date': next_weekday(today, 5, 5), 'start_time': time(16, 0), 'end_time': time(17, 30),
        'description': 'Long hours at a desk or on the phone strain the neck and lower back. In this practical '
                       'workshop you learn how to set up your chair and screen, simple stretches for the workday, '
                       'and the early signs that need attention.',
        'max_participants': 25,
    }),
]

for title, image, values in EVENTS:
    event, created = upsert(Event, {'title': title}, {
        **values, 'clinic': clinic, 'presenter': presenter, 'language': 'en', 'fees': Decimal('0'),
        'registration_required': True, 'waitlist_enabled': True, 'status': 'published', 'is_published': True,
    }, image)
    print(('created ' if created else 'updated ') + title)
