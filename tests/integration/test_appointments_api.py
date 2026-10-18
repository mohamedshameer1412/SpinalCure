"""Booking paths re-validate on the server: staff API, reschedule, status flow, public form."""
import json
from datetime import time

import pytest
from django.urls import reverse

from appointments.models import Appointment, DoctorAvailability
from spinalcure.utils import encode_b64uuid
from tests.conftest_helpers import make_patient, make_practitioner, next_weekday

API = '/en/appointments/api/bookings/'


@pytest.fixture
def doc(db):
    d = make_practitioner()
    DoctorAvailability.objects.create(practitioner=d, day_of_week=0, start_time=time(9), end_time=time(11), slot_duration_minutes=30)
    return d


def _post(client, **data):
    return client.post(API, json.dumps(data), content_type='application/json')


def test_api_rejects_double_booking_and_outside_hours(users, client, doc):
    client.force_login(users['receptionist'])
    p = make_patient()
    monday = str(next_weekday(0))
    base = dict(patient=str(p.pk), practitioner=str(doc.pk), appointment_date=monday, status='scheduled')
    assert _post(client, appointment_time='09:00', **base).status_code == 201
    r = _post(client, appointment_time='09:15', **base)
    assert r.status_code == 400 and 'no longer available' in str(r.json())
    assert _post(client, appointment_time='13:00', **base).status_code == 400
    assert Appointment.objects.count() == 1


def test_status_transitions_and_reschedule(users, client, doc):
    client.force_login(users['receptionist'])
    monday = next_weekday(0)
    a = Appointment.objects.create(practitioner=doc, appointment_date=monday, appointment_time=time(9), guest_name='G')
    Appointment.objects.create(practitioner=doc, appointment_date=monday, appointment_time=time(10), guest_name='H')
    url = f'{API}{encode_b64uuid(a.pk)}/'
    # moving onto a taken slot fails, onto a free one works
    assert client.post(url + 'reschedule/', {'date': str(monday), 'time': '10:00'}).status_code == 400
    r = client.post(url + 'reschedule/', {'date': str(monday), 'time': '10:30'})
    assert r.status_code == 200 and Appointment.objects.get(pk=a.pk).appointment_time == time(10, 30)
    # scheduled -> cancelled ok; cancelled -> confirmed rejected
    assert client.patch(url, json.dumps({'status': 'cancelled'}), content_type='application/json').status_code == 200
    assert client.patch(url, json.dumps({'status': 'confirmed'}), content_type='application/json').status_code == 400
    assert client.post(url + 'reschedule/', {'date': str(monday), 'time': '09:00'}).status_code == 400


def test_staff_role_cannot_book(users, client, doc):
    client.force_login(users['staff'])
    assert _post(client, guest_name='x', appointment_date=str(next_weekday(0)), appointment_time='09:00').status_code == 403


def test_calendar_date_range(users, client, doc):
    client.force_login(users['receptionist'])
    m1, m2 = next_weekday(0, 1), next_weekday(0, 3)
    for d in (m1, m2):
        Appointment.objects.create(practitioner=doc, appointment_date=d, appointment_time=time(9), guest_name='G')
    data = client.get(API, {'start': str(m1), 'end': str(next_weekday(0, 2))}).json()
    assert [a['appointment_date'] for a in data] == [str(m1)]


def test_public_booking_validates_and_does_not_touch_patient(client, doc):
    p = make_patient(email='real@example.com')
    url = reverse('book_appointment_ajax')
    monday = str(next_weekday(0))
    body = dict(name='Attacker', phone='9876543210', email='attacker@evil.com', date=monday, time='09:00',
                practitioner_id=encode_b64uuid(doc.pk))
    r = client.post(url, json.dumps(body), content_type='application/json')
    assert r.json()['status'] == 'success'
    p.refresh_from_db()
    assert p.email == 'real@example.com'  # unauthenticated form must not change the record
    r = client.post(url, json.dumps(body), content_type='application/json')
    assert r.status_code == 409  # slot now taken
    body.update(time='23:00')
    assert client.post(url, json.dumps(body), content_type='application/json').status_code == 409


def test_slot_api_accepts_both_id_formats(client, doc):
    monday = str(next_weekday(0))
    for pid in (str(doc.pk), encode_b64uuid(doc.pk)):
        r = client.get(reverse('api_available_slots'), {'date': monday, 'practitioner': pid})
        assert r.json()['available_slots'][0] == '09:00'
    assert client.get(reverse('api_available_slots'), {'date': monday, 'practitioner': 'bogus'}).status_code == 400


def test_availability_page_manages_shifts_and_leave(users, login, doc):
    c = login(users['clinic_admin'])
    url = reverse('doctor_availability')
    pid = encode_b64uuid(doc.pk)
    c.post(url, {'practitioner_id': pid, 'action': 'add_shift', 'day_of_week': 2, 'start_time': '17:00',
                 'end_time': '19:00', 'slot_duration_minutes': 20, 'buffer_minutes': 0})
    assert DoctorAvailability.objects.filter(practitioner=doc, day_of_week=2).count() == 1
    c.post(url, {'practitioner_id': pid, 'action': 'add_shift', 'day_of_week': 2, 'start_time': '18:00',
                 'end_time': '20:00', 'slot_duration_minutes': 20, 'buffer_minutes': 0})
    assert DoctorAvailability.objects.filter(practitioner=doc, day_of_week=2).count() == 1  # overlap rejected
    monday = next_weekday(0)
    c.post(url, {'practitioner_id': pid, 'action': 'add_leave', 'start_date': str(monday), 'end_date': str(monday)})
    assert doc.leaves.count() == 1


def test_doctor_only_sees_own_schedule(users, login, doc):
    other = make_practitioner(name='Other', email='other@test.com')
    resp = login(users['doctor']).get(reverse('doctor_availability'), {'practitioner_id': encode_b64uuid(other.pk)})
    assert resp.context['selected_doc'] == doc  # users['doctor'] email matches `doc`
    assert list(resp.context['practitioners']) == [doc]
