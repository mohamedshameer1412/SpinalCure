"""Notification centre, preferences, outbox delivery/retry/dedupe and the scheduled command."""
import json
from datetime import time, timedelta
from unittest import mock

import pytest
from django.core import mail
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from notifications.models import EmailOutbox, Notification, NotificationPreference
from notifications.services import notify_users, queue_email, retry_failed
from spinalcure.utils import encode_b64uuid
from tests.conftest_helpers import make_patient, make_practitioner, next_weekday


def test_notify_respects_prefs_and_dedupes(users):
    u = users['receptionist']
    NotificationPreference.objects.create(user=u, event='appointment_missed', in_app=True, email=False)
    for _ in range(2):
        notify_users([u], 'appointment_missed', 'Outcome needed', 'x', '/en/appointments/', dedupe_key='k1')
    assert Notification.objects.filter(user=u).count() == 1
    assert len(mail.outbox) == 0  # email turned off
    notify_users([u], 'admin_alert', 'Alert', url='https://evil.example')
    assert Notification.objects.get(event='admin_alert').url == ''  # external links dropped
    assert len(mail.outbox) == 1


def test_outbox_failure_is_logged_and_retried(db):
    with mock.patch('notifications.services.EmailMultiAlternatives.send', side_effect=OSError('smtp down')):
        row = queue_email('p@example.com', 'appointment_reminder', 'Reminder', 'text', dedupe_key='r1')
    row.refresh_from_db()
    assert row.status == 'failed' and 'smtp down' in row.last_error and row.attempts == 1
    assert queue_email('p@example.com', 'appointment_reminder', 'Reminder', 'text', dedupe_key='r1') is None
    assert retry_failed() == 1
    row.refresh_from_db()
    assert row.status == 'sent' and len(mail.outbox) == 1


def test_center_actions_and_isolation(users, login):
    me, other = users['doctor'], users['receptionist']
    mine = Notification.objects.create(user=me, event='admin_alert', title='Mine', url='/en/patients/')
    theirs = Notification.objects.create(user=other, event='admin_alert', title='Theirs')
    c = login(me)
    assert 'Mine' in c.get(reverse('notification_center')).content.decode()
    assert c.get(reverse('notification_open', args=[theirs.pk])).status_code == 404
    r = c.get(reverse('notification_open', args=[mine.pk]))
    assert r['Location'] == '/en/patients/'
    mine.refresh_from_db()
    assert mine.is_read
    c.post(reverse('notification_action'), {'action': 'archive', 'id': mine.pk})
    mine.refresh_from_db()
    assert mine.is_archived
    c.post(reverse('notification_action'), {'action': 'read', 'next': '//evil.com'})
    theirs.refresh_from_db()
    assert not theirs.is_read  # bulk read only touches my rows


def test_preferences_page_saves(users, login):
    c = login(users['doctor'])
    c.post(reverse('notification_preferences'), {'in_app_admin_alert': 'on'})
    p = NotificationPreference.objects.get(user=users['doctor'], event='admin_alert')
    assert p.in_app and not p.email


def test_bell_shows_unread_count(users, login):
    Notification.objects.create(user=users['doctor'], event='admin_alert', title='Hello')
    html = login(users['doctor']).get(reverse('dashboard')).content.decode()
    assert '1 unread' in html


def test_cancel_and_reschedule_notify(users, client):
    doc = make_practitioner()
    patient = make_patient(email='pat@example.com')
    client.force_login(users['receptionist'])
    monday = next_weekday(0)
    a = Appointment.objects.create(practitioner=doc, patient=patient, appointment_date=monday, appointment_time=time(10))
    url = f'/en/appointments/api/bookings/{encode_b64uuid(a.pk)}/'
    assert client.post(url + 'reschedule/', {'date': str(monday), 'time': '11:00'}).status_code == 200
    assert client.patch(url, json.dumps({'status': 'cancelled'}), content_type='application/json').status_code == 200
    subjects = [m.subject for m in mail.outbox if m.to == ['pat@example.com']]
    assert any('rescheduled' in s for s in subjects) and any('cancelled' in s for s in subjects)
    assert Notification.objects.filter(user=users['doctor'], event='appointment_cancelled').exists()  # practitioner's login


def test_scheduled_command_reminds_once_and_flags_missed(users):
    doc = make_practitioner()
    patient = make_patient(email='pat@example.com')
    now = timezone.localtime()
    soon = now + timedelta(hours=3)
    Appointment.objects.create(practitioner=doc, patient=patient, appointment_date=soon.date(),
                               appointment_time=soon.time().replace(second=0, microsecond=0))
    past = now - timedelta(hours=3)
    missed = Appointment(practitioner=doc, guest_name='G', appointment_date=past.date(),
                         appointment_time=past.time().replace(second=0, microsecond=0))
    Appointment.objects.bulk_create([missed])  # bypass past-date validation, as old data would
    for _ in range(2):
        call_command('send_notifications', stdout=open('/dev/null', 'w'))
    assert len([m for m in mail.outbox if 'Reminder' in m.subject]) == 1
    assert Notification.objects.filter(event='appointment_missed').count() == len([u for u in users.values() if u.can('appointments_manage')])


def test_staff_invite_and_public_booking_alert(users, login):
    login(users['owner']).post(reverse('admin_user_create'), {'username': 'newbie', 'email': 'newbie@test.com',
                                                               'password': 'Str0ng-Pass-2026!', 'role': 'staff'})
    assert any(m.to == ['newbie@test.com'] and 'Welcome' in m.subject for m in mail.outbox)
    assert all('Str0ng-Pass-2026!' not in m.body for m in mail.outbox)


def test_deliveries_page_admin_only(users, login):
    assert login(users['receptionist']).get(reverse('notification_deliveries')).status_code == 302
    assert login(users['clinic_admin']).get(reverse('notification_deliveries')).status_code == 200
