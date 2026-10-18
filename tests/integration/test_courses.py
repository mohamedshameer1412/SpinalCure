import json
from datetime import date, timedelta

import pytest
from django.urls import reverse

from clinic.models import ClinicProfile
from courses import service
from courses.models import Course, CourseBatch, CourseFeedback, CourseRegistration
from events.service import EventError
from notifications.models import Notification
from spinalcure.utils import encode_b64uuid


@pytest.fixture(autouse=True)
def _quiet(settings):
    settings.NOTIFY_SEND_ON_COMMIT = False


@pytest.fixture
def batch(db):
    ClinicProfile.objects.create(name='Clinic', address='x', phone='9876543210')
    c = Course.objects.create(title='Acupressure Basics', short_description='Learn', is_published=True)
    return CourseBatch.objects.create(course=c, name='Batch 1', start_date=date.today() + timedelta(days=14),
                                      is_active=True, is_published=True, max_participants=2)


def post(client, batch, **kw):
    body = {'name': 'Asha Raman', 'phone': '9876543210', 'email': 'asha@example.com', **kw}
    return client.post(reverse('course_register_ajax', args=[batch.course.pk]), data=json.dumps(body),
                       content_type='application/json')


def test_register_confirms_and_returns_private_link(client, batch):
    r = post(client, batch)
    assert r.status_code == 200 and r.json()['outcome'] == 'confirmed'
    reg = CourseRegistration.objects.get()
    assert reg.access_token in r.json()['manage_url'] and reg.phone_key == '9876543210'
    assert Notification.objects.get(event_type='course_registered').email == 'asha@example.com'


def test_capacity_waitlist_fifo_promotion(batch):
    regs = [service.register(batch, name=f'S{i}', phone=f'900000000{i}', email=f's{i}@example.com') for i in range(1, 5)]
    assert [r.status for r in regs] == ['confirmed', 'confirmed', 'waitlisted', 'waitlisted']
    service.cancel_registration(regs[0])
    for r in regs: r.refresh_from_db()
    assert [r.status for r in regs] == ['cancelled', 'confirmed', 'confirmed', 'waitlisted']
    assert batch.registration_count == 2                                   # never above capacity
    assert Notification.objects.filter(event_type='course_promoted').count() == 1


def test_duplicate_phone_or_email_rejected_but_reregister_after_cancel(client, batch):
    assert post(client, batch).status_code == 200
    assert post(client, batch, name='Other One').json()['code'] == 'duplicate'
    assert post(client, batch, phone='9111111111').json()['code'] == 'duplicate'
    reg = CourseRegistration.objects.get()
    service.cancel_registration(reg)
    assert post(client, batch).status_code == 200


@pytest.mark.parametrize('patch', [{'name': ''}, {'phone': 'x'}, {'email': 'bad'}])
def test_validation(client, batch, patch):
    assert post(client, batch, **patch).status_code == 400


def test_closed_when_no_active_or_completed_batch(client, batch):
    CourseBatch.objects.update(is_active=False)
    assert post(client, batch).status_code == 400
    CourseBatch.objects.update(is_active=True, start_date=date.today() - timedelta(days=60), end_date=date.today() - timedelta(days=30))
    r = post(client, batch)
    assert r.status_code == 400 and r.json()['code'] == 'closed'


def test_csrf_enforced_and_get_rejected(batch):
    from django.test import Client
    url = reverse('course_register_ajax', args=[batch.course.pk])
    assert Client(enforce_csrf_checks=True).post(url, data='{}', content_type='application/json').status_code == 403
    assert Client().get(url).status_code == 405


def test_old_leaky_endpoints_removed(client, batch):
    base = f'/en/clinic/courses/{encode_b64uuid(batch.course.pk)}/'
    for tail in ('verify-registration/', 'feedback/'):
        assert client.post(base + tail, data='{}', content_type='application/json').status_code == 404


def test_feedback_only_via_token_after_completion(client, batch):
    reg = service.register(batch, name='Asha Raman', phone='9444455555', email='private@example.com')
    url = reverse('course_registration_manage', args=[reg.access_token])
    client.post(url, {'action': 'feedback', 'rating': '5'})
    assert CourseFeedback.objects.count() == 0                              # batch not completed / feedback closed
    CourseBatch.objects.filter(pk=batch.pk).update(start_date=date.today() - timedelta(days=60),
                                                   end_date=date.today() - timedelta(days=30), feedback_enabled=True)
    client.post(url, {'action': 'feedback', 'rating': '5', 'comment': 'Great'})
    fb = CourseFeedback.objects.get()
    assert fb.registration == reg and fb.reviewer_name == 'Asha Raman' and not fb.is_published
    client.post(url, {'action': 'feedback', 'rating': '1'})
    assert CourseFeedback.objects.count() == 1
    assert client.get(reverse('course_registration_manage', args=['bad'])).status_code == 404
    page = client.get(url).content.decode()
    assert '9444455555' not in page and 'private@example.com' not in page   # page never prints contact details


def test_cancel_before_start_only(client, batch):
    reg = service.register(batch, name='Asha Raman', phone='9876543210')
    client.post(reverse('course_registration_manage', args=[reg.access_token]), {'action': 'cancel'})
    reg.refresh_from_db(); assert reg.status == 'cancelled'
    reg2 = service.register(batch, name='Bala Kumar', phone='9000000002')
    CourseBatch.objects.filter(pk=batch.pk).update(start_date=date.today() - timedelta(days=1))
    with pytest.raises(EventError):
        service.cancel_registration(reg2)
    assert service.cancel_registration(reg2, by_staff=True).status == 'cancelled'
