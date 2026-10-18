from datetime import date, datetime, time, timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from appointments import scheduling as sch
from appointments.models import Appointment, BookingSettings, DoctorAvailability
from clinic.models import ClinicProfile, Practitioner
from notifications.models import Notification
from patients.models import Patient, Session

TZ = timezone.get_default_timezone()


@pytest.fixture(autouse=True)
def _quiet(settings):
    settings.NOTIFY_SEND_ON_COMMIT = False


@pytest.fixture
def setup(db):
    ClinicProfile.objects.create(name='Clinic', address='x', phone='9876543210')
    doc = Practitioner.objects.create(name='Dr Rao', is_active=True)
    p = Patient.objects.create(name='Asha', phone='9876543210', email='asha@example.com')
    return doc, p


def appt_at(doc, p, when, created=None, status='scheduled'):
    a = Appointment.objects.create(patient=p, practitioner=doc, appointment_date=when.date(),
                                   appointment_time=when.time(), duration_minutes=30, status=status)
    if created:
        Appointment.objects.filter(pk=a.pk).update(created_at=created)
    return a


def run():
    out = StringIO(); call_command('send_reminders', stdout=out); return out.getvalue()


def local_now():
    return timezone.localtime(timezone.now(), TZ).replace(second=0, microsecond=0, tzinfo=None)


def test_reminder_sent_once_per_offset_even_if_run_repeatedly(setup):
    doc, p = setup
    appt_at(doc, p, local_now() + timedelta(hours=1, minutes=30), created=timezone.now() - timedelta(days=3))
    run(); run(); run()
    # default offsets 1440 and 120: 120 min before is not reached yet (90 min away => 120 offset is due), 1440 also due
    keys = set(Notification.objects.filter(event_type='appointment_reminder').values_list('dedupe_key', flat=True))
    assert len(keys) == Notification.objects.filter(event_type='appointment_reminder').count() == 2


def test_not_yet_due_reminder_is_not_sent(setup):
    doc, p = setup
    appt_at(doc, p, local_now() + timedelta(days=5), created=timezone.now() - timedelta(days=1))
    run()
    assert Notification.objects.filter(event_type='appointment_reminder').count() == 0


def test_booking_made_inside_reminder_window_gets_no_stale_reminder(setup):
    doc, p = setup
    appt_at(doc, p, local_now() + timedelta(minutes=90))            # created just now; 24h reminder moment already passed
    run()
    offsets = [n.dedupe_key.split(':')[-1] for n in Notification.objects.filter(event_type='appointment_reminder')]
    assert offsets == ['120'] or offsets == []                       # at most the 2h one, never the 24h one


def test_cancelled_and_past_appointments_get_no_reminders(setup):
    doc, p = setup
    appt_at(doc, p, local_now() + timedelta(hours=1), created=timezone.now() - timedelta(days=3), status='cancelled')
    appt_at(doc, p, local_now() - timedelta(hours=1), created=timezone.now() - timedelta(days=3))
    run()
    assert Notification.objects.filter(event_type='appointment_reminder').count() == 0


def test_configurable_offsets(setup):
    doc, p = setup
    cfg = BookingSettings.get(); cfg.reminder_offsets_minutes = '30'; cfg.save()
    appt_at(doc, p, local_now() + timedelta(minutes=20), created=timezone.now() - timedelta(days=3))
    run()
    assert [n.dedupe_key.rsplit(':', 1)[-1] for n in Notification.objects.all()] == ['30']


def test_followup_reminder_only_without_future_booking(setup):
    doc, p = setup
    s = Session.objects.create(patient=p, session_date=date.today() - timedelta(days=7),
                               next_appointment_date=date.today() + timedelta(days=1))
    run(); run()
    assert Notification.objects.filter(event_type='treatment_followup').count() == 1
    Notification.objects.all().delete()
    appt_at(doc, p, local_now() + timedelta(days=1), created=timezone.now() - timedelta(days=1))
    run()
    assert Notification.objects.filter(event_type='treatment_followup').count() == 0


def test_missed_appointment_alerts_staff_by_default_and_does_not_change_status(setup):
    from django.contrib.auth import get_user_model
    get_user_model().objects.create_user(username='r', email='r@example.com', password='x', role='receptionist')
    doc, p = setup
    a = appt_at(doc, p, local_now() - timedelta(hours=3), created=timezone.now() - timedelta(days=3))
    run(); run()
    assert Notification.objects.filter(event_type='appointment_missed_staff').count() == 1
    a.refresh_from_db(); assert a.status == 'scheduled'


def test_auto_no_show_when_enabled_notifies_patient_once(setup):
    doc, p = setup
    cfg = BookingSettings.get(); cfg.auto_mark_no_show = True; cfg.save()
    a = appt_at(doc, p, local_now() - timedelta(hours=3), created=timezone.now() - timedelta(days=3))
    run(); run()
    a.refresh_from_db(); assert a.status == 'no_show'
    assert Notification.objects.filter(event_type='appointment_missed').count() == 1
