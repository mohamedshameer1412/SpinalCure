from datetime import date, datetime, time, timedelta

import pytest
from django.utils import timezone

from appointments import scheduling as sch
from appointments.models import Appointment, BookingSettings, DoctorAvailability, TimeOff
from clinic.models import ClinicProfile, Practitioner
from notifications.models import Notification
from patients.models import Patient

TZ = timezone.get_default_timezone()
# A fixed "now": Monday 2030-01-07 08:00 clinic time.
NOW = timezone.make_aware(datetime(2030, 1, 7, 8, 0), TZ)
MON, TUE, WED = date(2030, 1, 7), date(2030, 1, 8), date(2030, 1, 9)


@pytest.fixture(autouse=True)
def _quiet(settings):
    settings.NOTIFY_SEND_ON_COMMIT = False


@pytest.fixture
def clinic(db):
    return ClinicProfile.objects.create(name='Test Clinic', address='1 Main St', phone='9876543210')


@pytest.fixture
def doc(clinic):
    return Practitioner.objects.create(name='Dr Rao', is_active=True)


@pytest.fixture
def doc2(clinic):
    return Practitioner.objects.create(name='Dr Mehta', is_active=True)


@pytest.fixture
def patient(db):
    return Patient.objects.create(name='Asha', phone='9876543210', email='asha@example.com')


def shift(doc, day=0, start=(10, 0), end=(13, 0), slot=30, **kw):
    return DoctorAvailability.objects.create(
        practitioner=doc, day_of_week=day, start_time=time(*start), end_time=time(*end),
        slot_duration_minutes=slot, **kw)


def starts(slots):
    return [s.label for s in slots]


def test_generates_slots_from_shift(doc):
    shift(doc)
    assert starts(sch.generate_slots(doc, MON, now=NOW)) == ['10:00', '10:30', '11:00', '11:30', '12:00', '12:30']


def test_no_shift_means_no_slots(doc):
    assert sch.generate_slots(doc, MON, now=NOW) == []
    shift(doc, day=1)                       # Tuesday only
    assert sch.generate_slots(doc, MON, now=NOW) == []


def test_multiple_shifts_per_day_and_break(doc):
    shift(doc, start=(10, 0), end=(13, 0), break_start=time(11, 0), break_end=time(11, 30))
    shift(doc, start=(17, 30), end=(19, 0))
    assert starts(sch.generate_slots(doc, MON, now=NOW)) == \
        ['10:00', '10:30', '11:30', '12:00', '12:30', '17:30', '18:00', '18:30']


def test_appointment_type_filter(doc):
    shift(doc, appointment_type='online')
    assert sch.generate_slots(doc, MON, 'physical', now=NOW) == []
    assert len(sch.generate_slots(doc, MON, 'online', now=NOW)) == 6


def test_recurring_validity_window(doc):
    shift(doc, valid_from=date(2030, 2, 1))
    assert sch.generate_slots(doc, MON, now=NOW) == []
    assert len(sch.generate_slots(doc, date(2030, 2, 4), now=timezone.make_aware(datetime(2030, 2, 1), TZ))) == 6


def test_min_notice_and_past_and_max_advance(doc):
    shift(doc, start=(8, 0), end=(10, 0))
    cfg = BookingSettings.get(); cfg.min_notice_minutes = 60; cfg.save()
    assert starts(sch.generate_slots(doc, MON, now=NOW)) == ['09:00', '09:30']        # 08:00 + 60m notice
    assert sch.generate_slots(doc, date(2030, 1, 6), now=NOW) == []                   # yesterday
    cfg.max_advance_days = 3; cfg.save()
    assert sch.generate_slots(doc, date(2030, 1, 14), now=NOW) == []


def test_leave_blocks_whole_day_and_partial(doc):
    shift(doc)
    TimeOff.objects.create(practitioner=doc, start_date=MON, end_date=MON, start_time=time(10, 0), end_time=time(11, 0))
    assert starts(sch.generate_slots(doc, MON, now=NOW)) == ['11:00', '11:30', '12:00', '12:30']
    TimeOff.objects.create(practitioner=doc, start_date=MON, end_date=MON, kind='leave')
    assert sch.generate_slots(doc, MON, now=NOW) == []


def test_clinic_wide_holiday_blocks_every_practitioner(doc, doc2):
    shift(doc); shift(doc2)
    TimeOff.objects.create(practitioner=None, kind='holiday', start_date=MON, end_date=TUE)
    assert sch.generate_slots(doc, MON, now=NOW) == [] and sch.generate_slots(doc2, MON, now=NOW) == []


def test_multi_day_leave_covers_middle_days(doc):
    shift(doc, day=1)
    TimeOff.objects.create(practitioner=doc, start_date=MON, end_date=WED)
    assert sch.generate_slots(doc, TUE, now=NOW) == []


def test_booking_removes_slot_and_buffer_applies(doc, patient):
    shift(doc, buffer_minutes=15)
    sch.book(practitioner=doc, day=MON, start_time=time(10, 30), patient=patient, now=NOW)
    got = starts(sch.generate_slots(doc, MON, now=NOW))
    assert '10:30' not in got and '10:00' not in got and '11:00' not in got   # 15-min buffer eats neighbours
    assert '11:30' in got


def test_max_appointments_per_shift(doc, patient):
    shift(doc, max_appointments=1)
    sch.book(practitioner=doc, day=MON, start_time=time(10, 0), patient=patient, now=NOW)
    assert sch.generate_slots(doc, MON, now=NOW) == []


def test_double_booking_is_rejected_server_side(doc, patient):
    shift(doc)
    sch.book(practitioner=doc, day=MON, start_time=time(10, 0), patient=patient, now=NOW)
    with pytest.raises(sch.SchedulingError) as e:
        sch.book(practitioner=doc, day=MON, start_time=time(10, 0), guest_name='B', guest_phone='9000000001', now=NOW)
    assert e.value.code == 'conflict'
    assert Appointment.objects.count() == 1


def test_overlapping_longer_booking_is_rejected(doc, patient):
    shift(doc)
    sch.book(practitioner=doc, day=MON, start_time=time(10, 30), patient=patient, now=NOW)
    with pytest.raises(sch.SchedulingError) as e:
        sch.book(practitioner=doc, day=MON, start_time=time(10, 0), duration=60, guest_name='B',
                 guest_phone='9000000001', now=NOW)
    assert e.value.code == 'conflict'


def test_cancelled_slot_is_bookable_again(doc, patient):
    shift(doc)
    a = sch.book(practitioner=doc, day=MON, start_time=time(10, 0), patient=patient, now=NOW)
    sch.cancel(a, now=NOW)
    sch.book(practitioner=doc, day=MON, start_time=time(10, 0), guest_name='B', guest_phone='9000000001', now=NOW)


@pytest.mark.parametrize('day,t,code', [
    (date(2030, 1, 6), time(10, 0), 'past'),
    (MON, time(8, 30), 'too_soon'),
    (MON, time(9, 0), 'outside_hours'),
    (MON, time(13, 0), 'outside_hours'),
    (TUE, time(10, 0), 'closed'),
    (date(2031, 6, 2), time(10, 0), 'too_far'),
])
def test_invalid_requests_get_specific_errors(doc, patient, day, t, code):
    shift(doc)
    with pytest.raises(sch.SchedulingError) as e:
        sch.book(practitioner=doc, day=day, start_time=t, patient=patient, now=NOW)
    assert e.value.code == code


def test_leave_is_enforced_at_booking_time(doc, patient):
    shift(doc)
    TimeOff.objects.create(practitioner=doc, start_date=MON, end_date=MON)
    with pytest.raises(sch.SchedulingError) as e:
        sch.book(practitioner=doc, day=MON, start_time=time(10, 0), patient=patient, now=NOW)
    assert e.value.code == 'blocked'


def test_frontend_visibility_is_not_trusted(doc, patient):
    """A slot hidden from the picker (e.g. break) cannot be booked by crafting the request."""
    shift(doc, break_start=time(11, 0), break_end=time(11, 30))
    with pytest.raises(sch.SchedulingError):
        sch.book(practitioner=doc, day=MON, start_time=time(11, 0), patient=patient, now=NOW)


def test_staff_can_book_outside_hours_but_never_over_a_conflict_or_leave(doc, patient):
    shift(doc)
    ok = sch.book(practitioner=doc, day=MON, start_time=time(9, 0), patient=patient, ignore_hours=True,
                  ignore_notice=True, now=NOW)
    assert ok.appointment_time == time(9, 0)
    with pytest.raises(sch.SchedulingError):
        sch.book(practitioner=doc, day=MON, start_time=time(9, 0), guest_name='B', guest_phone='9000000001',
                 ignore_hours=True, ignore_notice=True, now=NOW)
    TimeOff.objects.create(practitioner=doc, start_date=MON, end_date=MON, start_time=time(14, 0), end_time=time(15, 0))
    with pytest.raises(sch.SchedulingError):
        sch.book(practitioner=doc, day=MON, start_time=time(14, 0), guest_name='C', guest_phone='9000000002',
                 ignore_hours=True, ignore_notice=True, now=NOW)


def test_public_cannot_use_staff_overrides(doc):
    shift(doc)
    with pytest.raises(sch.SchedulingError):
        sch.book(practitioner=doc, day=MON, start_time=time(9, 0), guest_name='B', guest_phone='9000000001',
                 source='public', ignore_hours=True, ignore_notice=True, now=NOW)


def test_idempotent_request_key_returns_same_booking(doc, patient):
    shift(doc)
    a = sch.book(practitioner=doc, day=MON, start_time=time(10, 0), patient=patient, request_key='k1', now=NOW)
    b = sch.book(practitioner=doc, day=MON, start_time=time(10, 0), patient=patient, request_key='k1', now=NOW)
    assert a.pk == b.pk and Appointment.objects.count() == 1
    assert Notification.objects.filter(event_type='appointment_booked').count() == 1


def test_any_available_doctor_picks_one_with_the_slot(doc, doc2, patient):
    shift(doc2)                       # only Dr Mehta works Monday
    a = sch.book(day=MON, start_time=time(10, 0), patient=patient, now=NOW)
    assert a.practitioner == doc2
    with pytest.raises(sch.SchedulingError) as e:              # the only working doctor is now busy at 10:00
        sch.book(day=MON, start_time=time(10, 0), guest_name='B', guest_phone='9000000001', now=NOW)
    assert e.value.code == 'conflict'
    b = sch.book(day=MON, start_time=time(10, 30), guest_name='B', guest_phone='9000000001', now=NOW)
    assert b.practitioner == doc2


def test_public_booking_limit_per_contact(doc):
    shift(doc)
    cfg = BookingSettings.get(); cfg.max_active_per_contact = 2; cfg.save()
    for t in (time(10, 0), time(10, 30)):
        sch.book(practitioner=doc, day=MON, start_time=t, guest_name='B', guest_phone='9000000001',
                 source='public', now=NOW)
    with pytest.raises(sch.SchedulingError) as e:
        sch.book(practitioner=doc, day=MON, start_time=time(11, 0), guest_name='B', guest_phone='9000000001',
                 source='public', now=NOW)
    assert e.value.code == 'limit'


def test_public_booking_can_be_disabled(doc):
    shift(doc)
    cfg = BookingSettings.get(); cfg.allow_public_booking = False; cfg.save()
    with pytest.raises(sch.SchedulingError):
        sch.book(practitioner=doc, day=MON, start_time=time(10, 0), guest_name='B', guest_phone='9000000001',
                 source='public', now=NOW)


def test_guest_requires_contact():
    with pytest.raises(sch.SchedulingError) as e:
        sch.book(day=MON, start_time=time(10, 0), guest_name='B', now=NOW)
    assert e.value.code == 'invalid_contact'


# ── state machine ──────────────────────────────────────────────────────────────────────────────

def test_state_machine_transitions(doc, patient):
    shift(doc)
    a = sch.book(practitioner=doc, day=MON, start_time=time(10, 0), patient=patient, now=NOW)
    a = sch.confirm(a)
    assert a.status == 'confirmed' and a.confirmed_at
    with pytest.raises(sch.SchedulingError):
        sch.complete(a)                                   # not started yet
    sch.cancel(a, now=NOW)
    with pytest.raises(sch.SchedulingError) as e:
        sch.confirm(Appointment.objects.get(pk=a.pk))     # cancelled is terminal
    assert e.value.code == 'invalid_transition'


def test_complete_and_no_show_only_after_start(doc, patient, monkeypatch):
    shift(doc, start=(10, 0), end=(11, 0))
    a = sch.book(practitioner=doc, day=MON, start_time=time(10, 0), patient=patient, now=NOW)
    with pytest.raises(sch.SchedulingError) as e:
        sch.mark_no_show(a)                                   # real clock is long before 2030
    assert e.value.code == 'too_early'
    monkeypatch.setattr(timezone, 'now', lambda: timezone.make_aware(datetime(2030, 1, 7, 12, 0), TZ))
    assert sch.complete(a).status == 'completed'
    with pytest.raises(sch.SchedulingError):
        sch.mark_no_show(Appointment.objects.get(pk=a.pk))      # completed is terminal


def test_patient_cancel_cutoff(doc, patient):
    shift(doc, start=(10, 0), end=(12, 0))
    a = sch.book(practitioner=doc, day=MON, start_time=time(10, 0), patient=patient, now=NOW)
    late = timezone.make_aware(datetime(2030, 1, 7, 9, 0), TZ)          # 1h before; cutoff is 2h
    with pytest.raises(sch.SchedulingError) as e:
        sch.cancel(a, by_patient=True, now=late)
    assert e.value.code == 'too_late'
    assert sch.cancel(a, by_patient=False, now=late).status == 'cancelled'   # staff may still cancel


def test_reschedule_moves_and_links_and_frees_old_slot(doc, patient):
    shift(doc)
    a = sch.book(practitioner=doc, day=MON, start_time=time(10, 0), patient=patient, now=NOW)
    b = sch.reschedule(a, day=MON, start_time=time(11, 0), now=NOW)
    a.refresh_from_db()
    assert a.status == 'rescheduled' and b.status == 'scheduled' and b.rescheduled_from_id == a.pk
    assert '10:00' in starts(sch.generate_slots(doc, MON, now=NOW)) and '11:00' not in starts(sch.generate_slots(doc, MON, now=NOW))
    assert Notification.objects.filter(event_type='appointment_rescheduled').count() == 1


def test_reschedule_into_taken_slot_fails_and_keeps_original(doc, patient):
    shift(doc)
    a = sch.book(practitioner=doc, day=MON, start_time=time(10, 0), patient=patient, now=NOW)
    sch.book(practitioner=doc, day=MON, start_time=time(11, 0), guest_name='B', guest_phone='9000000001', now=NOW)
    with pytest.raises(sch.SchedulingError) as e:
        sch.reschedule(a, day=MON, start_time=time(11, 0), now=NOW)
    assert e.value.code == 'conflict'
    a.refresh_from_db()
    assert a.status == 'scheduled' and Appointment.objects.count() == 2


def test_reschedule_can_shift_within_own_slot_range(doc, patient):
    shift(doc)
    a = sch.book(practitioner=doc, day=MON, start_time=time(10, 0), duration=60, patient=patient, now=NOW)
    b = sch.reschedule(a, day=MON, start_time=time(10, 30), now=NOW)       # overlaps its own old time: allowed
    assert b.appointment_time == time(10, 30)


# ── notifications & model ──────────────────────────────────────────────────────────────────────

def test_booking_notifies_patient_and_staff_without_clinical_text(doc, patient):
    shift(doc)
    User = __import__('django.contrib.auth', fromlist=['get_user_model']).get_user_model()
    User.objects.create_user(username='r', email='r@example.com', password='x', role='receptionist')
    patient.chief_complaint = 'sciatica'; patient.save()
    sch.book(practitioner=doc, day=MON, start_time=time(10, 0), patient=patient, reason='sciatica', now=NOW)
    texts = ' '.join(Notification.objects.values_list('title', flat=True)) + ' '.join(Notification.objects.values_list('body', flat=True))
    assert 'sciatica' not in texts
    assert set(Notification.objects.values_list('event_type', flat=True)) == {'appointment_booked', 'appointment_booked_staff'}


def test_guest_booking_notifies_by_email_and_str_works(doc):
    shift(doc)
    a = sch.book(practitioner=doc, day=MON, start_time=time(10, 0), guest_name='Guest G', guest_email='g@example.com', now=NOW)
    assert 'Guest G' in str(a)
    assert Notification.objects.get(event_type='appointment_booked').email == 'g@example.com'


def test_shift_validation(doc):
    from django.core.exceptions import ValidationError
    shift(doc)
    with pytest.raises(ValidationError):
        DoctorAvailability(practitioner=doc, day_of_week=0, start_time=time(12, 0), end_time=time(14, 0)).full_clean()
    with pytest.raises(ValidationError):
        DoctorAvailability(practitioner=doc, day_of_week=2, start_time=time(10, 0), end_time=time(9, 0)).full_clean()
    with pytest.raises(ValidationError):
        DoctorAvailability(practitioner=doc, day_of_week=2, start_time=time(10, 0), end_time=time(12, 0),
                           break_start=time(9, 0), break_end=time(9, 30)).full_clean()
    DoctorAvailability(practitioner=doc, day_of_week=0, start_time=time(17, 0), end_time=time(19, 0)).full_clean()


def test_timeoff_validation(doc):
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        TimeOff(practitioner=doc, start_date=TUE, end_date=MON).full_clean()
    with pytest.raises(ValidationError):
        TimeOff(practitioner=doc, start_date=MON, end_date=MON, start_time=time(9, 0)).full_clean()
