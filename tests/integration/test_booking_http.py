import json
from datetime import date, time, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from appointments.models import Appointment, BookingSettings, DoctorAvailability, TimeOff
from clinic.models import ClinicProfile, Practitioner
from notifications.models import Notification
from patients.models import Patient
from spinalcure.utils import encode_b64uuid

User = get_user_model()


def next_weekday(weekday, min_ahead=3):
    d = date.today() + timedelta(days=min_ahead)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


DAY = next_weekday(0)           # a Monday at least 3 days ahead
OTHER = next_weekday(2)         # a Wednesday: no shift


@pytest.fixture(autouse=True)
def _quiet(settings):
    settings.NOTIFY_SEND_ON_COMMIT = False


@pytest.fixture
def clinic(db):
    return ClinicProfile.objects.create(name='Test Clinic', address='1 Main St', phone='9876543210',
                                        email='clinic@example.com')


@pytest.fixture
def doc(clinic):
    d = Practitioner.objects.create(name='Dr Rao', email='rao@example.com', is_active=True)
    DoctorAvailability.objects.create(practitioner=d, day_of_week=0, start_time=time(10, 0), end_time=time(13, 0))
    return d


def mk(role, **kw):
    return User.objects.create_user(username=f'u_{role}', email=f'{role}@example.com', password='Str0ng!pass9',
                                    role=role, **kw)


def post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type='application/json')


BOOK = {'name': 'Guest G', 'phone': '9000000001', 'email': 'g@example.com', 'type': 'physical',
        'date': DAY.isoformat(), 'time': '10:00', 'notes': ''}


# ── slots API ──────────────────────────────────────────────────────────────────────────────────

def test_slots_api_uses_real_shifts(client, doc):
    r = client.get(reverse('api_available_slots'), {'date': DAY.isoformat(), 'practitioner': encode_b64uuid(doc.pk)})
    assert r.status_code == 200
    assert r.json()['available_slots'] == ['10:00', '10:30', '11:00', '11:30', '12:00', '12:30']


def test_slots_api_explains_closed_days_and_leave(client, doc):
    r = client.get(reverse('api_available_slots'), {'date': OTHER.isoformat()}).json()
    assert r['available_slots'] == [] and 'does not take bookings' in r['message']
    TimeOff.objects.create(practitioner=None, kind='holiday', start_date=DAY, end_date=DAY)
    r = client.get(reverse('api_available_slots'), {'date': DAY.isoformat()}).json()
    assert r['available_slots'] == [] and 'closed' in r['message']


@pytest.mark.parametrize('params,status', [
    ({}, 400), ({'date': 'nope'}, 400), ({'date': DAY.isoformat(), 'type': 'x'}, 400),
    ({'date': DAY.isoformat(), 'duration': '2'}, 400), ({'date': DAY.isoformat(), 'practitioner': 'garbage'}, 404),
    ({'date': DAY.isoformat(), 'practitioner': '00000000-0000-0000-0000-000000000000'}, 404),
])
def test_slots_api_rejects_bad_input_instead_of_falling_back(client, doc, params, status):
    assert client.get(reverse('api_available_slots'), params).status_code == status


# ── public booking ─────────────────────────────────────────────────────────────────────────────

def test_public_booking_creates_guest_appointment_and_notifies(client, doc):
    r = post_json(client, reverse('book_appointment_ajax'), {**BOOK, 'practitioner_id': encode_b64uuid(doc.pk)})
    assert r.status_code == 200 and r.json()['status'] == 'success'
    a = Appointment.objects.get()
    assert a.patient is None and a.guest_name == 'Guest G' and a.booked_via == 'public' and a.practitioner == doc
    kinds = set(Notification.objects.values_list('event_type', flat=True))
    assert {'appointment_booked', 'appointment_booked_clinic'} <= kinds
    assert Notification.objects.get(event_type='appointment_booked').email == 'g@example.com'
    assert '/appointments/manage/' in Notification.objects.get(event_type='appointment_booked').url


def test_public_booking_rejects_taken_and_invalid_slots_server_side(client, doc):
    url = reverse('book_appointment_ajax')
    assert post_json(client, url, BOOK).status_code == 200
    again = post_json(client, url, {**BOOK, 'phone': '9000000002', 'name': 'Other Person'})
    assert again.status_code in (409, 400) and again.json()['status'] == 'error'
    assert Appointment.objects.count() == 1
    assert post_json(client, url, {**BOOK, 'phone': '9000000003', 'time': '09:00'}).json()['code'] == 'outside_hours'
    assert post_json(client, url, {**BOOK, 'phone': '9000000003', 'date': OTHER.isoformat()}).json()['code'] == 'closed'
    past = (date.today() - timedelta(days=2)).isoformat()
    assert post_json(client, url, {**BOOK, 'phone': '9000000003', 'date': past}).json()['code'] == 'past'


@pytest.mark.parametrize('patch', [
    {'name': ''}, {'phone': 'abc'}, {'email': 'not-an-email'}, {'date': 'x'}, {'time': 'x'}, {'type': 'teleport'},
])
def test_public_booking_validates_input(client, doc, patch):
    assert post_json(client, reverse('book_appointment_ajax'), {**BOOK, **patch}).status_code == 400
    assert Appointment.objects.count() == 0


def test_public_booking_cannot_touch_an_existing_patient(client, doc):
    p = Patient.objects.create(name='Asha', phone='9000000001', email='asha@example.com')
    post_json(client, reverse('book_appointment_ajax'), {**BOOK, 'email': 'attacker@example.com'})
    p.refresh_from_db()
    assert p.email == 'asha@example.com'                      # not overwritten
    a = Appointment.objects.get()
    assert a.patient is None and not p.appointments.exists()  # booking not attached to the patient


def test_public_booking_honeypot_and_idempotency(client, doc):
    url = reverse('book_appointment_ajax')
    assert post_json(client, url, {**BOOK, 'website': 'http://spam'}).status_code == 200
    assert Appointment.objects.count() == 0
    for _ in range(2):
        post_json(client, url, {**BOOK, 'request_key': 'abc123'})
    assert Appointment.objects.count() == 1


def test_public_booking_requires_csrf_cookie_protection(doc):
    from django.test import Client
    strict = Client(enforce_csrf_checks=True)
    assert post_json(strict, reverse('book_appointment_ajax'), BOOK).status_code == 403


def test_get_not_allowed_on_booking(client):
    assert client.get(reverse('book_appointment_ajax')).status_code == 405


# ── self-service link ──────────────────────────────────────────────────────────────────────────

def _booked(client, doc):
    post_json(client, reverse('book_appointment_ajax'), BOOK)
    return Appointment.objects.get()


def test_manage_page_shows_only_booking_and_cancels(client, doc):
    a = _booked(client, doc)
    r = client.get(reverse('appointment_manage', args=[a.manage_token]))
    assert r.status_code == 200 and b'Guest G' in r.content
    assert b'9000000001' not in r.content and b'g@example.com' not in r.content
    r = client.post(reverse('appointment_manage', args=[a.manage_token]), {'action': 'cancel', 'reason': 'sick'})
    assert r.status_code == 302
    a.refresh_from_db(); assert a.status == 'cancelled' and a.cancel_reason == 'sick'


def test_manage_reschedule_and_slots(client, doc):
    a = _booked(client, doc)
    s = client.get(reverse('appointment_manage_slots', args=[a.manage_token]), {'date': DAY.isoformat()}).json()
    assert '10:00' in [x['value'] for x in s['slots']]       # its own slot is offered back to it
    r = client.post(reverse('appointment_manage', args=[a.manage_token]),
                    {'action': 'reschedule', 'date': DAY.isoformat(), 'time': '11:30'})
    assert r.status_code == 302
    a.refresh_from_db()
    assert a.status == 'rescheduled' and Appointment.objects.get(rescheduled_from=a).appointment_time == time(11, 30)


def test_manage_unknown_token_404_and_blocks_after_cutoff(client, doc):
    assert client.get(reverse('appointment_manage', args=['nope'])).status_code == 404
    a = _booked(client, doc)
    cfg = BookingSettings.get(); cfg.cancel_cutoff_hours = 24 * 30; cfg.save()   # everything is "too late"
    client.post(reverse('appointment_manage', args=[a.manage_token]), {'action': 'cancel'})
    a.refresh_from_db(); assert a.status == 'scheduled'


# ── staff API ──────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def staff_api():
    api = APIClient(); api.force_authenticate(mk('receptionist')); return api


@pytest.fixture
def patient(db):
    return Patient.objects.create(name='Asha', phone='9876543210', email='asha@example.com')


def test_staff_api_books_through_engine_and_hides_secret(staff_api, doc, patient):
    r = staff_api.post('/api/appointments/', {'patient': str(patient.pk), 'practitioner': str(doc.pk),
                                              'appointment_date': DAY.isoformat(), 'appointment_time': '10:00',
                                              'appointment_type': 'physical', 'reason': 'Review'}, format='json')
    assert r.status_code == 201, r.content
    assert 'manage_token' not in r.json() and 'request_key' not in r.json()
    assert Appointment.objects.get().booked_via == 'staff'


def test_staff_api_cannot_double_book_or_book_outside_hours(staff_api, doc, patient):
    body = {'patient': str(patient.pk), 'practitioner': str(doc.pk), 'appointment_date': DAY.isoformat(),
            'appointment_time': '10:00', 'appointment_type': 'physical'}
    assert staff_api.post('/api/appointments/', body, format='json').status_code == 201
    r = staff_api.post('/api/appointments/', body, format='json')
    assert r.status_code == 409 and r.json()['code'] == 'conflict'
    r = staff_api.post('/api/appointments/', {**body, 'appointment_time': '08:00'}, format='json')
    assert r.status_code == 400 and r.json()['code'] == 'outside_hours'
    r = staff_api.post('/api/appointments/', {**body, 'appointment_time': '08:00', 'allow_outside_hours': True}, format='json')
    assert r.status_code == 201                                  # explicit walk-in override
    r = staff_api.post('/api/appointments/', {**body, 'allow_outside_hours': True}, format='json')
    assert r.status_code == 409                                  # but never over a conflict


def test_staff_api_reschedule_status_and_delete_rules(staff_api, doc, patient):
    body = {'patient': str(patient.pk), 'practitioner': str(doc.pk), 'appointment_date': DAY.isoformat(),
            'appointment_time': '10:00', 'appointment_type': 'physical'}
    a = staff_api.post('/api/appointments/', body, format='json').json()
    pk = Appointment.objects.get().pk
    r = staff_api.patch(f'/api/appointments/{pk}/', {'appointment_time': '11:00'}, format='json')
    assert r.status_code == 200 and r.json()['appointment_time'].startswith('11:00')
    new_pk = Appointment.objects.get(status='scheduled').pk
    assert staff_api.patch(f'/api/appointments/{new_pk}/', {'status': 'confirmed'}, format='json').json()['status'] == 'confirmed'
    assert staff_api.patch(f'/api/appointments/{new_pk}/', {'status': 'completed'}, format='json').json()['code'] == 'too_early'
    assert staff_api.patch(f'/api/appointments/{new_pk}/', {'status': 'bogus'}, format='json').status_code == 400
    assert staff_api.patch(f'/api/appointments/{new_pk}/', {'appointment_time': '99:99'}, format='json').status_code == 400
    assert staff_api.delete(f'/api/appointments/{new_pk}/').status_code == 403      # receptionist cannot destroy history
    assert staff_api.post(f'/api/appointments/{new_pk}/cancel/', {'reason': 'x'}, format='json').status_code == 200


def test_staff_role_cannot_use_appointment_api():
    api = APIClient(); api.force_authenticate(mk('staff'))
    assert api.get('/api/appointments/').status_code == 403
    assert api.post('/api/appointments/', {}, format='json').status_code == 403


def test_status_cannot_be_set_via_create(staff_api, doc, patient):
    r = staff_api.post('/api/appointments/', {'patient': str(patient.pk), 'practitioner': str(doc.pk),
                                              'appointment_date': DAY.isoformat(), 'appointment_time': '10:00',
                                              'status': 'completed'}, format='json')
    assert r.status_code == 201 and r.json()['status'] == 'scheduled'


# ── availability management UI ─────────────────────────────────────────────────────────────────

SHIFT = {'day_of_week': 1, 'start_time': '09:00', 'end_time': '12:00', 'slot_duration_minutes': 20,
         'buffer_minutes': 0, 'appointment_type': 'both', 'is_available': 'on'}


def test_doctor_manages_own_schedule(client, doc):
    boss = mk('doctor', email='rao@example.com') if False else User.objects.create_user(
        username='rao', email='rao@example.com', password='Str0ng!pass9', role='doctor')
    client.force_login(boss)
    assert client.get(reverse('doctor_availability')).status_code == 200
    url = reverse('shift_save', args=[encode_b64uuid(doc.pk)])
    r = client.post(url, SHIFT)
    assert r.status_code == 302 and DoctorAvailability.objects.filter(practitioner=doc, day_of_week=1).count() == 1
    shift = DoctorAvailability.objects.get(practitioner=doc, day_of_week=1)
    client.post(url, {**SHIFT, 'shift_id': str(shift.pk), 'end_time': '13:00'})
    shift.refresh_from_db(); assert shift.end_time == time(13, 0)
    client.post(url, {**SHIFT, 'start_time': '10:00'})                     # overlaps -> rejected
    assert DoctorAvailability.objects.filter(practitioner=doc, day_of_week=1).count() == 1
    client.post(reverse('shift_delete', args=[encode_b64uuid(doc.pk), shift.pk]))
    assert not DoctorAvailability.objects.filter(pk=shift.pk).exists()


def test_doctor_cannot_edit_another_practitioners_schedule(client, doc):
    other = Practitioner.objects.create(name='Dr Other', email='other@example.com', is_active=True)
    client.force_login(User.objects.create_user(username='rao', email='rao@example.com', password='Str0ng!pass9', role='doctor'))
    client.post(reverse('shift_save', args=[encode_b64uuid(other.pk)]), SHIFT)
    assert not DoctorAvailability.objects.filter(practitioner=other).exists()
    r = client.post(reverse('timeoff_save', args=['clinic']), {'kind': 'holiday', 'start_date': DAY.isoformat(), 'end_date': DAY.isoformat()})
    assert not TimeOff.objects.exists()


def test_receptionist_cannot_open_availability(client, doc):
    client.force_login(mk('receptionist'))
    assert client.get(reverse('doctor_availability')).status_code == 302
    assert client.post(reverse('shift_save', args=[encode_b64uuid(doc.pk)]), SHIFT).status_code == 302
    assert not DoctorAvailability.objects.filter(day_of_week=1).exists()


def test_management_closes_clinic_and_sets_rules(client, doc, patient):
    from appointments import scheduling as sch
    sch.book(practitioner=doc, day=DAY, start_time=time(10, 0), patient=patient)
    client.force_login(mk('owner'))
    r = client.post(reverse('timeoff_save', args=['clinic']),
                    {'kind': 'holiday', 'start_date': DAY.isoformat(), 'end_date': DAY.isoformat(), 'reason': 'Diwali'},
                    follow=True)
    assert TimeOff.objects.get().practitioner is None
    assert any('existing appointment' in str(m) for m in r.context['messages'])          # clash warning, not silent
    assert Appointment.objects.get().status == 'scheduled'                              # nothing auto-cancelled
    r = client.get(reverse('api_available_slots'), {'date': DAY.isoformat()}).json()
    assert r['available_slots'] == []
    client.post(reverse('booking_settings_save'), {
        'min_notice_minutes': 30, 'max_advance_days': 60, 'default_duration_minutes': 30, 'cancel_cutoff_hours': 4,
        'max_active_per_contact': 2, 'allow_public_booking': 'on', 'reminder_offsets_minutes': '2880,60',
        'followup_lead_days': 3, 'missed_grace_minutes': 45})
    cfg = BookingSettings.get()
    assert cfg.reminder_offsets == [2880, 60] and cfg.cancel_cutoff_hours == 4 and not cfg.auto_mark_no_show
    client.post(reverse('booking_settings_save'), {'reminder_offsets_minutes': 'abc', 'min_notice_minutes': 1,
                                                   'max_advance_days': 1, 'default_duration_minutes': 1,
                                                   'cancel_cutoff_hours': 1, 'max_active_per_contact': 1,
                                                   'followup_lead_days': 1, 'missed_grace_minutes': 1})
    assert BookingSettings.get().reminder_offsets == [2880, 60]                          # invalid rules rejected


def test_state_changing_availability_endpoints_reject_get(client, doc):
    client.force_login(mk('owner'))
    assert client.get(reverse('shift_save', args=[encode_b64uuid(doc.pk)])).status_code == 405
    assert client.get(reverse('booking_settings_save')).status_code == 405
