"""Slot engine: availability, breaks, buffers, limits, leave, conflicts, past times."""
from datetime import time, timedelta

import pytest
from django.utils import timezone

from appointments.models import Appointment, DoctorAvailability, PractitionerLeave
from appointments.scheduling import available_slots, check_bookable
from tests.conftest_helpers import make_practitioner, next_weekday

pytestmark = pytest.mark.django_db


@pytest.fixture
def doc():
    d = make_practitioner()
    DoctorAvailability.objects.create(practitioner=d, day_of_week=0, start_time=time(9), end_time=time(11), slot_duration_minutes=30)
    DoctorAvailability.objects.create(practitioner=d, day_of_week=0, start_time=time(14), end_time=time(15), slot_duration_minutes=30)
    return d


def book(doc, day, t, minutes=30, status='scheduled'):
    return Appointment.objects.create(practitioner=doc, appointment_date=day, appointment_time=t,
                                      duration_minutes=minutes, status=status, guest_name='G')


def test_slots_follow_shifts_and_break(doc):
    monday = next_weekday(0)
    assert available_slots(monday, doc) == ['09:00', '09:30', '10:00', '10:30', '14:00', '14:30']
    assert available_slots(monday + timedelta(days=1), doc) == []  # configured doctor, no Tuesday shift


def test_booked_and_overlapping_slots_removed(doc):
    monday = next_weekday(0)
    book(doc, monday, time(9, 30), minutes=60)
    assert available_slots(monday, doc) == ['09:00', '10:30', '14:00', '14:30']
    book(doc, monday, time(14), status='cancelled')  # cancelled frees the slot
    assert '14:00' in available_slots(monday, doc)


def test_buffer_and_limit(doc):
    monday = next_weekday(0)
    shift = DoctorAvailability.objects.get(practitioner=doc, start_time=time(9))
    shift.buffer_minutes, shift.max_appointments = 15, 2
    shift.save()
    book(doc, monday, time(9))
    assert '09:30' not in available_slots(monday, doc)  # inside 15 min buffer
    book(doc, monday, time(10))
    assert [s for s in available_slots(monday, doc) if s < '12:00'] == []  # limit of 2 reached


def test_leave_and_clinic_holiday(doc):
    monday = next_weekday(0)
    leave = PractitionerLeave.objects.create(practitioner=doc, start_date=monday, end_date=monday)
    assert available_slots(monday, doc) == []
    leave.delete()
    PractitionerLeave.objects.create(practitioner=None, start_date=monday, end_date=monday + timedelta(days=2))
    assert available_slots(monday, doc) == [] and available_slots(monday) == []


def test_unconfigured_doctor_uses_clinic_hours():
    d = make_practitioner(name='New', email='new@test.com')
    monday = next_weekday(0)
    slots = available_slots(monday, d)
    assert slots[0] == '10:00' and '12:30' in slots and '12:45' not in slots  # 30 min must fit before 13:00
    assert available_slots(next_weekday(6), d) == []  # Sunday closed
    assert available_slots(monday, d, 'online')[0] == '09:00'


def test_check_bookable_messages(doc):
    monday = next_weekday(0)
    assert check_bookable(doc, monday, time(9), 30) is None
    book(doc, monday, time(9))
    assert 'no longer available' in check_bookable(doc, monday, time(9, 15), 30)
    assert 'outside working hours' in check_bookable(doc, monday, time(12), 30)
    assert 'past' in check_bookable(doc, timezone.localdate() - timedelta(days=1), time(9), 30)
    doc.is_active = False
    assert 'not taking' in check_bookable(doc, monday, time(10), 30)


def test_overlapping_shift_rejected(doc):
    from django.core.exceptions import ValidationError
    s = DoctorAvailability(practitioner=doc, day_of_week=0, start_time=time(10), end_time=time(12))
    with pytest.raises(ValidationError):
        s.full_clean()


@pytest.mark.django_db(transaction=True)
def test_concurrent_bookings_cannot_both_succeed():
    import threading
    from django.db import connection, transaction
    from appointments.scheduling import booking_lock
    d = make_practitioner(email='race@test.com')
    monday = next_weekday(0)
    barrier, results = threading.Barrier(4), []

    def attempt():
        try:
            barrier.wait()
            with booking_lock(d.pk, monday), transaction.atomic():
                if check_bookable(d, monday, time(10), 30) is None:
                    book(d, monday, time(10))
                    results.append('booked')
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results == ['booked']
    assert Appointment.objects.filter(practitioner=d, appointment_date=monday).count() == 1
