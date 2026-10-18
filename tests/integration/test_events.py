"""Events: capacity/waitlist, private meeting links, deadlines, cancellation, change notices, attendance."""
import json
from datetime import datetime, time, timedelta

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from events.models import Event, EventRegistration


def make_event(**kw):
    start = timezone.localtime() + timedelta(days=3)
    data = dict(title='Back pain webinar', event_type=Event.EVENT_TYPE_CHOICES[0][0], date=start.date(),
                start_time=time(10), end_time=time(11), is_online=True, meeting_link='https://meet.example.com/secret-room',
                venue='Online', is_published=True, max_participants=1)
    data.update(kw)
    return Event.objects.create(**data)


def reg(client, event, phone, email='a@example.com'):
    return client.post(reverse('event_register_ajax', args=[event.pk]),
                       json.dumps({'name': 'Asha', 'phone': phone, 'email': email}), content_type='application/json')


@pytest.mark.django_db
def test_capacity_waitlist_and_promotion(client):
    e = make_event()
    assert reg(client, e, '9000000001', 'first@example.com').json()['registration_status'] == 'confirmed'
    assert reg(client, e, '9000000002', 'second@example.com').json()['registration_status'] == 'waitlisted'
    assert reg(client, e, '9000000001').status_code == 409  # duplicate
    first = EventRegistration.objects.get(phone='9000000001')
    client.post(reverse('event_registration_manage', args=[first.access_token]), {'action': 'cancel'})
    assert EventRegistration.objects.get(phone='9000000002').status == 'confirmed'
    assert any('seat opened' in m.subject.lower() and m.to == ['second@example.com'] for m in mail.outbox)
    e.waitlist_enabled = False
    e.save()
    assert reg(client, e, '9000000003').status_code == 409


@pytest.mark.django_db
def test_meeting_link_is_private(client):
    e = make_event()
    assert 'secret-room' not in client.get(reverse('event_detail', args=[e.pk])).content.decode()
    assert 'secret-room' not in client.get(reverse('event_ics', args=[e.pk])).content.decode()
    reg(client, e, '9000000001')
    r = EventRegistration.objects.get()
    assert all('secret-room' not in m.body for m in mail.outbox)
    resp = client.get(reverse('event_join', args=[r.access_token]))
    assert 'secret-room' not in resp.get('Location', '')  # too early
    start = timezone.localtime() + timedelta(minutes=10)
    Event.objects.filter(pk=e.pk).update(date=start.date(), start_time=start.time(), end_time=(start + timedelta(hours=1)).time())
    assert client.get(reverse('event_join', args=[r.access_token]))['Location'] == 'https://meet.example.com/secret-room'
    r.refresh_from_db()
    assert r.attended is True
    assert client.get(reverse('event_join', args=['wrong-token'])).status_code == 404


@pytest.mark.django_db
def test_deadline_and_cancelled_event_block_registration(client):
    e = make_event(registration_deadline=timezone.now() - timedelta(hours=1))
    assert 'deadline' in reg(client, e, '9000000001').json()['message']
    e2 = make_event(is_cancelled=True)
    assert reg(client, e2, '9000000001').status_code == 409


def test_cancel_and_change_notify_registrants(users, login, client):
    e = make_event(max_participants=None)
    reg(client, e, '9000000001', 'one@example.com')
    c = login(users['doctor'])
    c.post(reverse('event_lifecycle', args=[e.pk]), {'action': 'cancel', 'reason': 'Presenter unwell'})
    e.refresh_from_db()
    assert e.is_cancelled and e.phase == 'cancelled'
    assert any(m.subject.startswith('Cancelled') and 'Presenter unwell' in m.body for m in mail.outbox)


def test_attendance_and_staff_permissions(users, login, client):
    e = make_event(max_participants=None)
    reg(client, e, '9000000001')
    r = EventRegistration.objects.get()
    login(users['receptionist']).post(reverse('event_registration_update', args=[r.pk]), {'action': 'attended'})
    r.refresh_from_db()
    assert r.attended is None  # receptionist cannot manage events
    login(users['doctor']).post(reverse('event_registration_update', args=[r.pk]), {'action': 'attended'})
    r.refresh_from_db()
    assert r.attended is True
    page = login(users['doctor']).get(reverse('event_registrations', args=[e.pk]), {'q': 'Asha'})
    assert page.status_code == 200  # search used a non-existent field before


@pytest.mark.django_db
def test_public_list_tabs(client):
    make_event(title='Future talk')
    make_event(title='Called off', is_cancelled=True)
    up = client.get(reverse('public_event_list')).content.decode()
    assert 'Future talk' in up and 'Called off' not in up
    assert 'Called off' in client.get(reverse('public_event_list'), {'tab': 'cancelled'}).content.decode()


def test_event_form_creates_online_event(users, login):
    day = (timezone.localdate() + timedelta(days=5)).isoformat()
    login(users['doctor']).post(reverse('event_create'), {
        'title': 'Webinar', 'event_type': Event.EVENT_TYPE_CHOICES[0][0], 'date': day, 'start_time': '18:00', 'end_time': '19:00',
        'is_online': 'on', 'meeting_link': 'https://meet.example.com/x', 'max_participants': '50', 'fees': '0',
        'is_published': 'on', 'waitlist_enabled': 'on', 'presenter': 'Dr. Arun', 'language': 'ta'})
    e = Event.objects.get(title='Webinar')
    assert e.is_online and e.language == 'ta' and e.presenter == 'Dr. Arun'


@pytest.mark.django_db
def test_course_capacity_waitlist(client):
    from courses.models import Course, CourseBatch, CourseRegistration
    c = Course.objects.create(title='Acupressure basics', description='x', is_published=True, fees=0)
    CourseBatch.objects.create(course=c, name='Jan', start_date=timezone.localdate() + timedelta(days=10), max_participants=1, is_active=True)
    url = reverse('course_register_ajax', args=[c.pk])
    body = lambda p: json.dumps({'name': 'S', 'phone': p, 'email': 's@example.com'})  # noqa: E731
    assert client.post(url, body('9000000001'), content_type='application/json').json()['status'] == 'success'
    r = client.post(url, body('9000000002'), content_type='application/json').json()
    assert r.get('registration_status') == 'waitlisted'
    assert CourseRegistration.objects.filter(status='confirmed').count() == 1
