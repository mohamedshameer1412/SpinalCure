"""Fill a DISPOSABLE demo database with synthetic data (never run against real data).

    DB_NAME=spinalcure_demo python demo/walkthrough/seed_demo.py

Creates: a demo super admin, 8 made-up patients with sittings, appointments and payments, one demo course with a batch,
students, attendance and a certificate. Every name, phone number and email is invented.
"""
import io
import os
import sys
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'spinalcure.settings')
os.environ['DJANGO_ENV'] = 'development'
if os.environ.get('DB_NAME', '') != 'spinalcure_demo':
    sys.exit('Refusing to seed: DB_NAME must be spinalcure_demo')
import django  # noqa: E402

django.setup()
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.files.base import ContentFile  # noqa: E402
from django.utils import timezone  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from appointments.models import Appointment  # noqa: E402
from clinic.models import ClinicProfile, Practitioner  # noqa: E402
from courses import ops, service  # noqa: E402
from courses.models import Course, CourseBatch, CourseSession, Student  # noqa: E402
from patients.models import Patient, Session  # noqa: E402
from payments.models import Payment  # noqa: E402

DEMO_EMAIL, DEMO_PASSWORD = os.environ.get('DEMO_EMAIL', 'demo.admin@spinalcure.local'), os.environ.get('DEMO_PASSWORD', 'Demo@12345')
User = get_user_model()
today = date.today()
clinic = ClinicProfile.objects.first()
doctor = Practitioner.objects.filter(is_active=True).first()

if not User.objects.filter(email=DEMO_EMAIL).exists():
    User.objects.create_superuser(username='demo.admin', email=DEMO_EMAIL, password=DEMO_PASSWORD, role='superadmin',
                                  first_name='Demo', last_name='Admin', is_verified=True)

PEOPLE = [
    ('Priya Natarajan', 'F', '9000000101', 'Lower back pain for three months, worse after sitting', 'Back Pain'),
    ('Karthik Subramanian', 'M', '9000000102', 'Neck stiffness and headaches from desk work', 'Neck Pain'),
    ('Lakshmi Venkatesh', 'F', '9000000103', 'Pain travelling down the right leg', 'Sciatica'),
    ('Arun Prakash', 'M', '9000000104', 'Right knee pain while climbing stairs', 'Knee Pain'),
    ('Meena Raghavan', 'F', '9000000105', 'Stiff shoulder, cannot lift the arm', 'Frozen Shoulder'),
    ('Vijay Anand', 'M', '9000000106', 'Slipped disc diagnosed on MRI', 'Slip Disc'),
    ('Divya Krishnan', 'F', '9000000107', 'Migraine twice a week', 'Migraine'),
    ('Suresh Babu', 'M', '9000000108', 'Hip pain on waking', 'Hip Pain'),
]
patients = []
for i, (name, gender, phone, complaint, _tag) in enumerate(PEOPLE):
    p, _ = Patient.objects.get_or_create(phone=phone, defaults=dict(
        name=name, gender=gender, email=f'demo.patient{i + 1}@example.com', address='12 Sample Street, Chennai 600001',
        reason_for_visit=complaint, attender_name='', attender_phone='', attender_relation='', chief_complaint=complaint,
        medical_history='None recorded', allergies='None known', registered_date=today - timedelta(days=60 - i * 5), notes=''))
    patients.append(p)
    if not p.sessions.exists():
        for n in range(1, 4 if i % 2 else 2):
            Session.objects.create(patient=p, session_number=n, session_date=today - timedelta(days=21 - n * 7 + i),
                                   acupoints_used='GB30, BL23, GV3', techniques_used='Classical needling',
                                   patient_feedback='Feeling lighter', practitioner_notes='Responding well')

slots = [time(10, 30), time(11, 0), time(11, 30), time(17, 30), time(18, 0), time(18, 30), time(19, 0), time(19, 30)]
if not Appointment.objects.exists():
    for i, p in enumerate(patients):
        day = today + timedelta(days=(0 if i < 3 else 1 + i % 3))
        if day.weekday() == 6:                                    # the clinic is closed on Sunday
            day += timedelta(days=1)
        Appointment.objects.create(patient=p, practitioner=doctor, appointment_date=day, appointment_time=slots[i],
                                   reason=p.chief_complaint[:60], notes='', status='confirmed' if i % 2 else 'scheduled')

if not Payment.objects.exists():
    for i, p in enumerate(patients[:6]):
        total = Decimal('1500') * (1 + i % 3)
        paid = total if i % 3 else total - Decimal('500')
        Payment.objects.create(patient=p, total_amount=total, amount_paid=paid, payment_date=today - timedelta(days=i * 3),
                               payment_mode=['cash', 'upi', 'card'][i % 3], manual_payer_name='', manual_payer_phone='',
                               receipt_number=f'DEMO-{1001 + i}', description='Acupuncture sittings', notes='')

# ── a demo course, batch, students, attendance and a certificate ────────────────────────────────
course, _ = Course.objects.get_or_create(title='Acupressure for Everyday Pain (Demo)', defaults=dict(
    short_description='A one-week demo workshop with synthetic students.', description='Demo course used only for this walkthrough.',
    platform='offline', fees=Decimal('4000'), duration='1 week', is_published=True, clinic=clinic))
if not course.batches.exists():
    batch = CourseBatch.objects.create(course=course, name='Demo batch', start_date=today + timedelta(days=3), is_active=True,
                                       is_published=True, max_participants=12, schedule_details='Weekdays, 10:30 am - 1:30 pm',
                                       min_attendance_percent=75)
    regs = [service.register(batch, name=n, phone=ph, email=em) for n, ph, em in (
        ('Anitha Selvam', '9000001001', 'demo.anitha@example.com'), ('Rahul Menon', '9000001002', 'demo.rahul@example.com'),
        ('Fatima Begum', '9000001003', ''))]
    # the batch has run: move its dates into the past so attendance and certificates can be shown
    CourseBatch.objects.filter(pk=batch.pk).update(start_date=today - timedelta(days=10), end_date=today - timedelta(days=1))
    batch.refresh_from_db()
    sessions = [CourseSession.objects.create(batch=batch, date=today - timedelta(days=9 - i), title=t)
                for i, t in enumerate(('Introduction and safety', 'Points for the neck and shoulders', 'Points for the back'))]
    ticks = {(str(s.pk), str(regs[0].pk)) for s in sessions} | {(str(s.pk), str(regs[1].pk)) for s in sessions[:2]}
    ops.save_attendance(batch, ticks)
    st = regs[0].student
    img = Image.new('RGB', (360, 440), (205, 226, 214))
    d = ImageDraw.Draw(img)
    d.ellipse((110, 70, 250, 210), fill=(120, 150, 135))
    d.ellipse((60, 230, 300, 520), fill=(120, 150, 135))
    buf = io.BytesIO()
    img.save(buf, 'JPEG')
    st.photo.save('demo.jpg', ContentFile(buf.getvalue()), save=False)
    st.designation, st.address, st.profile_completed_at = 'Physiotherapist', '5 Demo Garden, Chennai 600001', timezone.now()
    st.save()
    ops.issue_certificates(batch, send=False)
print('Demo data ready:', {m.__name__: m.objects.count() for m in (Patient, Appointment, Payment, Student)})
