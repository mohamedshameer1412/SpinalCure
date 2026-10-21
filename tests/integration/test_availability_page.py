"""The weekly-hours editor: Monday-Saturday morning 10:30-13:30 and evening 17:30-20:30, validation, leave."""
from datetime import date, time, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from appointments.models import DoctorAvailability, TimeOff
from clinic.models import ClinicProfile, Practitioner
from spinalcure.utils import encode_b64uuid

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def doc(db):
    ClinicProfile.objects.create(name='C', address='a', phone='9876543210', email='c@x.com')
    return Practitioner.objects.create(name='Dr Rao', email='rao@example.com', is_active=True)


@pytest.fixture
def owner(client):
    u = User.objects.create_user(username='own', email='own@x.com', password='Str0ng!pass9', role='owner')
    client.force_login(u)
    return client


def week(**over):
    """The clinic's real week: Mon-Sat both sessions, Sunday closed."""
    data = {'slot_minutes': '30'}
    for d in range(6):
        data.update({f'd{d}_open': 'on', f'd{d}_m_start': '10:30', f'd{d}_m_end': '13:30',
                     f'd{d}_e_start': '17:30', f'd{d}_e_end': '20:30'})
    data.update(over)
    return data


def url(doc):
    return reverse('weekly_save', args=[encode_b64uuid(doc.pk)])


def shifts(doc):
    return sorted((s.day_of_week, s.start_time, s.end_time, s.slot_duration_minutes)
                  for s in DoctorAvailability.objects.filter(practitioner=doc))


def test_page_renders_the_week_with_time_dropdowns(owner, doc):
    html = owner.get(reverse('doctor_availability')).content.decode()
    assert html.count('type="checkbox" name="d') == 7 and 'name="d6_e_end"' in html
    assert '<option value="10:30">10:30 AM</option>' in html and 'Save weekly hours' in html


def test_saving_the_clinic_week_creates_twelve_shifts_and_sunday_is_closed(owner, doc):
    r = owner.post(url(doc), week())
    assert r.status_code == 302
    got = shifts(doc)
    assert len(got) == 12 and not any(d == 6 for d, *_ in got)
    assert got[0] == (0, time(10, 30), time(13, 30), 30) and got[1] == (0, time(17, 30), time(20, 30), 30)
    page = owner.get(reverse('doctor_availability') + f'?practitioner_id={encode_b64uuid(doc.pk)}').content.decode()
    assert '<option value="17:30" selected>5:30 PM</option>' in page and '<option value="10:30" selected>10:30 AM</option>' in page


def test_saving_again_replaces_instead_of_duplicating(owner, doc):
    owner.post(url(doc), week())
    owner.post(url(doc), week(d0_e_start='', d0_e_end='', slot_minutes='45'))
    mon = [s for s in shifts(doc) if s[0] == 0]
    assert mon == [(0, time(10, 30), time(13, 30), 45)] and len(shifts(doc)) == 11


def test_a_day_can_be_switched_off(owner, doc):
    owner.post(url(doc), week())
    data = week(); del data['d2_open']
    owner.post(url(doc), data)
    assert not any(d == 2 for d, *_ in shifts(doc))


@pytest.mark.parametrize('over, message', [
    ({'d1_m_start': '13:30', 'd1_m_end': '10:30'}, 'end time must be after'),
    ({'d1_m_end': ''}, 'choose both'),
    ({'d1_m_start': '', 'd1_m_end': '', 'd1_e_start': '', 'd1_e_end': ''}, 'Choose a morning or an evening'),
    ({'d1_m_end': '18:00'}, 'from the list'),                       # morning times stop at 2 PM
    ({'d1_e_start': '10:30'}, 'from the list'),                     # evening times start at 2 PM
    ({'d1_m_start': 'sdfsdfdsf'}, 'from the list'),
    ({'d1_m_start': '10:30', 'd1_m_end': '10:45'}, 'shorter than one'),
])
def test_bad_input_is_rejected_per_day_and_nothing_changes(owner, doc, over, message):
    owner.post(url(doc), week())
    before = shifts(doc)
    r = owner.post(url(doc), week(slot_minutes='60', **over))
    assert r.status_code == 400 and message in r.content.decode()
    assert shifts(doc) == before                                   # the old week is still there, untouched


def test_unknown_appointment_length_is_rejected(owner, doc):
    assert owner.post(url(doc), week(slot_minutes='7')).status_code == 400
    assert not DoctorAvailability.objects.filter(practitioner=doc).exists()


def test_receptionist_cannot_change_hours_and_a_doctor_only_their_own(client, doc):
    other = Practitioner.objects.create(name='Dr Other', email='other@example.com', is_active=True)
    client.force_login(User.objects.create_user(username='rc', email='rc@x.com', password='Str0ng!pass9', role='receptionist'))
    client.post(url(doc), week())
    assert not DoctorAvailability.objects.exists()
    c2 = Client()
    c2.force_login(User.objects.create_user(username='rao', email='rao@example.com', password='Str0ng!pass9', role='doctor'))
    c2.post(url(other), week())
    assert not DoctorAvailability.objects.filter(practitioner=other).exists()
    c2.post(url(doc), week())
    assert DoctorAvailability.objects.filter(practitioner=doc).count() == 12


def test_leave_needs_only_a_start_date_and_rejects_backwards_ranges(owner, doc):
    start = date.today() + timedelta(days=3)
    leave = reverse('timeoff_save', args=[encode_b64uuid(doc.pk)])
    owner.post(leave, {'kind': 'leave', 'start_date': start.isoformat(), 'end_date': '', 'reason': 'Conference'})
    off = TimeOff.objects.get()
    assert off.start_date == off.end_date == start and off.practitioner == doc
    owner.post(leave, {'kind': 'leave', 'start_date': start.isoformat(), 'end_date': (start - timedelta(days=2)).isoformat()})
    assert TimeOff.objects.count() == 1
    owner.post(reverse('timeoff_save', args=['clinic']), {'start_date': start.isoformat(), 'end_date': start.isoformat(), 'reason': 'Holiday'})
    assert TimeOff.objects.filter(practitioner__isnull=True, kind='holiday').count() == 1
    owner.post(reverse('timeoff_delete', args=[off.pk]))
    assert TimeOff.objects.filter(practitioner=doc).count() == 0


def test_appointment_list_survives_an_appointment_without_a_patient(owner, doc):
    from appointments.models import Appointment
    Appointment.objects.create(patient=None, practitioner=doc, appointment_date=date.today() + timedelta(days=1),
                               appointment_time=time(10, 30), status='scheduled')
    r = owner.get(reverse('appointment_list'))
    assert r.status_code == 200
    assert 'Patient record not found' in r.content.decode()
