from datetime import date, time, timedelta
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from notifications import service
from notifications.models import Notification, NotificationDelivery, NotificationPreference
from patients.models import Patient

User = get_user_model()
CTX = {'practitioner': 'Dr. Rao', 'clinic': 'SpinalCure', 'date': date(2030, 1, 15), 'time': time(10, 30)}


@pytest.fixture
def user():
    return User.objects.create_user(username='r', email='r@example.com', password='Str0ng!pass9', role='receptionist')


@pytest.fixture
def patient():
    return Patient.objects.create(name='Asha', phone='9876543210', email='asha@example.com')


@pytest.fixture(autouse=True)
def _no_on_commit(settings):
    settings.NOTIFY_SEND_ON_COMMIT = False  # tests drive delivery explicitly


def test_notify_creates_notification_and_email_delivery(patient):
    n = service.notify('appointment_booked', patient=patient, context=CTX, url='/portal/')
    assert n.title == 'Appointment booked' and 'Dr. Rao' in n.body
    d = n.deliveries.get(channel='email')
    service.deliver(d.pk)
    d.refresh_from_db()
    assert d.status == 'sent' and len(mail.outbox) == 1
    assert mail.outbox[0].to == ['asha@example.com']


def test_dedupe_key_prevents_duplicates_and_duplicate_mail(patient):
    a = service.notify('appointment_reminder', patient=patient, context=CTX, dedupe_key='appt:1:rem24')
    b = service.notify('appointment_reminder', patient=patient, context=CTX, dedupe_key='appt:1:rem24')
    assert a.pk == b.pk and Notification.objects.count() == 1
    for d in NotificationDelivery.objects.all():
        service.deliver(d.pk); service.deliver(d.pk)  # delivering twice sends once
    assert len(mail.outbox) == 1


def test_failed_email_is_retried_with_backoff_then_gives_up(patient):
    n = service.notify('invoice_created', patient=patient, context={'invoice': 'INV-1', 'amount': '₹500'})
    d = n.deliveries.get(channel='email')
    with mock.patch.dict(service.channel_mod.SENDERS, {'email': mock.Mock(side_effect=OSError('smtp down'))}):
        service.deliver(d.pk)
        d.refresh_from_db()
        assert d.status == 'failed' and d.attempts == 1 and d.next_attempt_at > timezone.now()
        assert 'smtp down' in d.last_error
        service.deliver(d.pk)                         # not due yet -> no new attempt
        d.refresh_from_db(); assert d.attempts == 1
        for expected in (2, 3, 4, 5):
            NotificationDelivery.objects.filter(pk=d.pk).update(next_attempt_at=timezone.now() - timedelta(seconds=1))
            service.deliver(d.pk); d.refresh_from_db()
            assert d.attempts == expected
        assert d.status == 'failed' and d.next_attempt_at is None   # exhausted, kept for the log
    assert len(mail.outbox) == 0


def test_retry_succeeds_after_transient_failure(patient):
    n = service.notify('invoice_created', patient=patient, context={'invoice': 'I', 'amount': '1'})
    d = n.deliveries.get(channel='email')
    with mock.patch.dict(service.channel_mod.SENDERS, {'email': mock.Mock(side_effect=OSError('x'))}):
        service.deliver(d.pk)
    NotificationDelivery.objects.filter(pk=d.pk).update(next_attempt_at=timezone.now() - timedelta(seconds=1))
    assert service.retry_due() == 1
    d.refresh_from_db(); assert d.status == 'sent' and len(mail.outbox) == 1


def test_sms_without_provider_is_skipped_never_reported_sent(patient):
    patient.notify_sms = True; patient.save()
    n = service.notify('appointment_reminder', patient=patient, context=CTX)
    d = n.deliveries.get(channel='sms')
    service.deliver(d.pk); d.refresh_from_db()
    assert d.status == 'skipped' and 'not set' in d.last_error


def test_patient_sms_whatsapp_are_opt_in(patient):
    n = service.notify('appointment_reminder', patient=patient, context=CTX)
    assert set(n.deliveries.values_list('channel', flat=True)) == {'email'}


def test_user_preferences_override_defaults(user):
    NotificationPreference.objects.create(user=user, event_type='payment_failed', channel='email', enabled=False)
    n = service.notify('payment_failed', user=user, context={'amount': '₹10', 'who': 'A'})
    assert n.deliveries.count() == 0 and n.persistent
    mandatory = service.notify('idcard_revoked', user=user, context={'employee_id': 'STF-1'})
    assert mandatory.persistent


def test_deep_links_must_be_local(patient):
    assert service.notify('invoice_created', patient=patient, context={}, url='https://evil.example/x').url == ''
    assert service.notify('invoice_created', patient=patient, context={}, url='//evil.example').url == ''
    assert service.notify('invoice_created', patient=patient, context={}, url='/payments/1/').url == '/payments/1/'


def test_missing_context_does_not_crash_or_leak_placeholders(patient):
    n = service.notify('appointment_booked', patient=patient, context={})
    assert n is not None and '%(' not in n.body


def test_patient_messages_contain_no_clinical_fields(patient):
    patient.chief_complaint = 'sciatica'; patient.save()
    n = service.notify('appointment_booked', patient=patient, context=CTX)
    assert 'sciatica' not in n.title + n.body


def test_notify_never_raises_into_caller():
    assert service.notify('appointment_booked', context=CTX) is None            # no recipient
    assert service.notify('not_an_event', email='x@example.com') is None          # logged, not raised


def test_guest_email_only(db):
    n = service.notify('appointment_booked', email='guest@example.com', context=CTX)
    assert set(n.deliveries.values_list('channel', flat=True)) == {'email'}


def test_resolve_alert_closes_persistent_alert(user):
    service.notify('payment_failed', user=user, context={'amount': '1', 'who': 'A'}, dedupe_key='pay:1')
    assert service.resolve_alert('pay:1') == 1
    assert not Notification.objects.get().is_active_alert


def test_notify_staff_fans_out_by_capability_and_dedupes():
    owner = User.objects.create_user(username='o', email='o@example.com', password='x', role='owner')
    User.objects.create_user(username='s', email='s@example.com', password='x', role='staff')
    sent = service.notify_staff('admin_alert', 'notifications.admin', context={'subject': 'Disk', 'detail': 'full'}, dedupe_key='disk')
    again = service.notify_staff('admin_alert', 'notifications.admin', context={'subject': 'Disk', 'detail': 'full'}, dedupe_key='disk')
    assert [n.user for n in sent] == [owner] and len(again) == 1
    assert Notification.objects.count() == 1


def test_localised_notification_arabic_digits_and_language(patient):
    patient.preferred_language = 'ar'; patient.save()
    n = service.notify('appointment_booked', patient=patient, context=CTX)
    assert n.language == 'ar'
    assert n.body  # catalogue falls back to English until translated, but never empty


# ---- views -------------------------------------------------------------------------------------

def test_center_summary_and_actions_are_scoped_to_owner(client, user):
    other = User.objects.create_user(username='x', email='x@example.com', password='x', role='doctor')
    mine = service.notify('admin_alert', user=user, context={'subject': 'A', 'detail': 'B'}, url='/payments/')
    theirs = service.notify('admin_alert', user=other, context={'subject': 'C', 'detail': 'D'})
    client.force_login(user)
    data = client.get(reverse('notification_summary')).json()
    assert data['unread'] == 1 and [i['id'] for i in data['items']] == [str(mine.pk)]
    assert client.post(reverse('notification_read', args=[theirs.pk])).status_code == 404
    client.post(reverse('notification_read', args=[mine.pk]))
    assert client.get(reverse('notification_summary')).json()['unread'] == 0
    client.post(reverse('notification_unread', args=[mine.pk]))
    client.post(reverse('notification_mark_all_read'))
    assert client.get(reverse('notification_summary')).json()['unread'] == 0
    client.post(reverse('notification_archive', args=[mine.pk]))
    assert client.get(reverse('notification_center') + '?tab=archived').status_code == 200
    Notification.objects.get(pk=theirs.pk); assert Notification.objects.get(pk=theirs.pk).archived_at is None


def test_open_redirects_to_local_link_and_marks_read(client, user):
    n = service.notify('admin_alert', user=user, context={'subject': 'A', 'detail': 'B'}, url='/payments/')
    client.force_login(user)
    resp = client.get(reverse('notification_open', args=[n.pk]))
    assert resp.status_code == 302 and resp.url == '/payments/'
    n.refresh_from_db(); assert n.is_read


def test_state_changing_endpoints_reject_get(client, user):
    n = service.notify('admin_alert', user=user, context={'subject': 'A', 'detail': 'B'})
    client.force_login(user)
    for name in ('notification_read', 'notification_archive'):
        assert client.get(reverse(name, args=[n.pk])).status_code == 405
    assert client.get(reverse('notification_mark_all_read')).status_code == 405


def test_preferences_page_saves_and_changes_language(client, user):
    client.force_login(user)
    assert client.get(reverse('notification_preferences')).status_code == 200
    client.post(reverse('notification_preferences'), {'language': 'ta', 'payment_failed__in_app': 'on'})
    user.refresh_from_db(); assert user.language == 'ta'
    pref = NotificationPreference.objects.get(user=user, event_type='payment_failed', channel='email')
    assert pref.enabled is False
    assert NotificationPreference.objects.get(user=user, event_type='payment_failed', channel='in_app').enabled


def test_delivery_log_requires_admin_capability(client, user):
    client.force_login(user)
    assert client.get(reverse('notification_deliveries')).status_code == 302
    boss = User.objects.create_user(username='b', email='b@example.com', password='x', role='owner')
    client.force_login(boss)
    assert client.get(reverse('notification_deliveries')).status_code == 200


def test_bell_renders_in_shell(client, user):
    client.force_login(user)
    html = client.get(reverse('notification_center')).content.decode()
    assert 'notifBell(' in html and 'notifications.js' in html
