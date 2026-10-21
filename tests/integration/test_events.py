import json
from datetime import date, datetime, time, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from clinic.models import ClinicProfile
from events import service
from events.models import Event, EventFeedback, EventRegistration
from notifications.models import Notification

User = get_user_model()
TZ = timezone.get_default_timezone()


@pytest.fixture(autouse=True)
def _quiet(settings):
    settings.NOTIFY_SEND_ON_COMMIT = False


@pytest.fixture
def clinic(db):
    return ClinicProfile.objects.create(name='Test Clinic', address='1 Main St', phone='9876543210')


def mk(role):
    return User.objects.create_user(username=f'u_{role}', email=f'{role}@example.com', password='Str0ng!pass9', role=role)


def make_event(**kw):
    defaults = dict(title='Spine Webinar', event_type='webinar', date=date.today() + timedelta(days=10),
                    start_time=time(10, 0), end_time=time(11, 0), is_online=True,
                    meeting_link='https://meet.example.com/secret-room', meeting_passcode='4321',
                    access_instructions='Use your registered name.', status='published', max_participants=2)
    defaults.update(kw)
    return Event.objects.create(**defaults)


def reg_json(client, event, **kw):
    body = {'name': 'Asha Raman', 'phone': '9876543210', 'email': 'asha@example.com', **kw}
    return client.post(reverse('event_register_ajax', args=[event.pk]), data=json.dumps(body), content_type='application/json')


# ── lifecycle / model ──────────────────────────────────────────────────────────────────────────

def test_status_is_source_of_truth_for_is_published(clinic):
    e = make_event(status='draft'); assert e.is_published is False
    e.status = 'published'; e.save(); assert e.is_published is True
    e.status = 'cancelled'; e.save(); assert e.is_published is False


def test_phase_uses_event_timezone(clinic):
    now = timezone.now()
    e = make_event(date=timezone.localdate(), start_time=time(0, 0), end_time=time(23, 59), timezone='Asia/Kolkata')
    assert e.phase in ('live', 'upcoming', 'completed')
    past = make_event(title='Old', date=date.today() - timedelta(days=3))
    assert past.phase == 'completed'
    assert make_event(title='C', status='cancelled').phase == 'cancelled'


def test_validation_rules(clinic):
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError):                       # online + published needs a link
        make_event(meeting_link='').full_clean()
    with pytest.raises(ValidationError):                       # in-person needs a venue
        Event(title='x', date=date.today() + timedelta(days=2), start_time=time(9), end_time=time(10), venue='').full_clean()
    with pytest.raises(ValidationError):                       # deadline after start
        e = make_event(); e.registration_deadline = e.starts_at + timedelta(hours=1); e.full_clean()
    with pytest.raises(ValidationError):                       # unknown timezone
        e = make_event(); e.timezone = 'Mars/Base'; e.full_clean()
    with pytest.raises(ValidationError):                       # past creation
        Event(title='x', date=date.today() - timedelta(days=1), start_time=time(9), end_time=time(10), venue='v').full_clean()


# ── registration ───────────────────────────────────────────────────────────────────────────────

def test_registration_confirms_notifies_and_returns_private_link(client, clinic):
    e = make_event()
    r = reg_json(client, e)
    assert r.status_code == 200 and r.json()['outcome'] == 'confirmed'
    reg = EventRegistration.objects.get()
    assert reg.status == 'confirmed' and reg.access_token and reg.phone_key == '9876543210'
    assert reg.access_token in r.json()['manage_url']
    n = Notification.objects.get(event_type='event_registered')
    assert n.email == 'asha@example.com' and reg.access_token in n.url
    assert 'secret-room' not in n.body + n.title + n.url        # link never goes into notifications


def test_capacity_waitlist_and_fifo_promotion(client, clinic):
    e = make_event(max_participants=2)
    a = service.register(e, name='A One', phone='9000000001', email='a@example.com')
    b = service.register(e, name='B Two', phone='9000000002', email='b@example.com')
    c = service.register(e, name='C Three', phone='9000000003', email='c@example.com')
    d = service.register(e, name='D Four', phone='9000000004', email='d@example.com')
    assert [a.status, b.status, c.status, d.status] == ['confirmed', 'confirmed', 'waitlisted', 'waitlisted']
    assert Notification.objects.filter(event_type='event_waitlisted').count() == 2
    service.cancel_registration(a)
    c.refresh_from_db(); d.refresh_from_db()
    assert c.status == 'confirmed' and d.status == 'waitlisted'            # oldest waitlisted first
    assert Notification.objects.filter(event_type='event_promoted').count() == 1
    assert e.confirmed_count == 2                                          # never over capacity


def test_full_event_without_waitlist_rejects(client, clinic):
    e = make_event(max_participants=1, waitlist_enabled=False)
    service.register(e, name='A One', phone='9000000001')
    r = reg_json(client, e, phone='9000000002', email='x@example.com')
    assert r.status_code == 409 and r.json()['code'] == 'full'


def test_raising_capacity_promotes_waitlist(clinic, client):
    e = make_event(max_participants=1)
    service.register(e, name='A One', phone='9000000001', email='a@example.com')
    w = service.register(e, name='B Two', phone='9000000002', email='b@example.com')
    e.max_participants = 3; e.save()
    service.promote_waitlist(e)
    w.refresh_from_db(); assert w.status == 'confirmed'


def test_duplicate_registration_by_phone_or_email_is_rejected(client, clinic):
    e = make_event(max_participants=None)
    assert reg_json(client, e).status_code == 200
    assert reg_json(client, e, name='Someone Else').json()['code'] == 'duplicate'
    assert reg_json(client, e, phone='9111111111').json()['code'] == 'duplicate'          # same email
    assert reg_json(client, e, phone='+91 98765-43210', email='other@example.com').json()['code'] == 'duplicate'
    assert EventRegistration.objects.count() == 1


def test_cancelled_registration_can_register_again(client, clinic):
    e = make_event(max_participants=None)
    reg = service.register(e, name='A One', phone='9000000001')
    service.cancel_registration(reg)
    service.register(e, name='A One', phone='9000000001')
    assert EventRegistration.objects.filter(status='confirmed').count() == 1


@pytest.mark.parametrize('kw,code', [
    ({'status': 'draft'}, 'closed'), ({'status': 'cancelled'}, 'closed'), ({'status': 'archived'}, 'closed'),
])
def test_cannot_register_when_not_published(clinic, kw, code):
    e = make_event(**kw)
    with pytest.raises(service.EventError) as exc:
        service.register(e, name='A One', phone='9000000001')
    assert exc.value.code == code


def test_deadline_and_ended_enforced_server_side(clinic):
    e = make_event()
    Event.objects.filter(pk=e.pk).update(registration_deadline=timezone.now() - timedelta(minutes=1))
    e.refresh_from_db()
    with pytest.raises(service.EventError) as exc:
        service.register(e, name='A One', phone='9000000001')
    assert exc.value.code == 'deadline'
    past = make_event(title='Old', date=date.today() - timedelta(days=2))
    with pytest.raises(service.EventError) as exc:
        service.register(past, name='A One', phone='9000000001')
    assert exc.value.code == 'ended'


@pytest.mark.parametrize('patch', [{'name': ''}, {'phone': 'abc'}, {'email': 'bad'}, {'phone': '12'}])
def test_registration_input_validated(client, clinic, patch):
    assert reg_json(client, make_event(), **patch).status_code == 400
    assert EventRegistration.objects.count() == 0


def test_honeypot_and_csrf_and_method(client, clinic):
    e = make_event()
    assert reg_json(client, e, website='spam').status_code == 200 and EventRegistration.objects.count() == 0
    from django.test import Client
    assert Client(enforce_csrf_checks=True).post(reverse('event_register_ajax', args=[e.pk]), data='{}',
                                                 content_type='application/json').status_code == 403
    assert client.get(reverse('event_register_ajax', args=[e.pk])).status_code == 405


def test_draft_events_are_invisible_publicly(client, clinic):
    d = make_event(status='draft')
    assert client.get(reverse('event_detail', args=[d.pk])).status_code == 404
    assert reg_json(client, d).status_code == 404
    assert client.get(reverse('event_ics', args=[d.pk])).status_code == 404


# ── meeting link protection ────────────────────────────────────────────────────────────────────

SECRET = 'meet.example.com/secret-room'


def test_meeting_link_never_on_public_surfaces(client, clinic):
    e = make_event(description='Join us')
    for url in (reverse('event_detail', args=[e.pk]), reverse('public_event_list'), reverse('event_ics', args=[e.pk])):
        assert SECRET.encode() not in client.get(url).content, url
    api = client.get('/api/events/')
    assert api.status_code == 200 and SECRET not in api.content.decode() and '4321' not in api.content.decode()
    assert SECRET not in client.get(f'/api/events/{encode(e)}/').content.decode()


def encode(e):
    from spinalcure.utils import encode_b64uuid
    return encode_b64uuid(e.pk)


def test_registrant_sees_link_only_in_join_window(client, clinic):
    e = make_event()
    reg = service.register(e, name='A One', phone='9000000001')
    page = client.get(reverse('event_registration_manage', args=[reg.access_token])).content.decode()
    assert SECRET not in page and 'appears here from' in page                      # 10 days early
    soon = timezone.now() + timedelta(minutes=10)
    local = soon.astimezone(e.tz)
    end = min(local + timedelta(hours=1), local.replace(hour=23, minute=59, second=0))   # never wraps past midnight
    Event.objects.filter(pk=e.pk).update(date=local.date(), start_time=local.time().replace(microsecond=0),
                                         end_time=end.time().replace(microsecond=0))
    page = client.get(reverse('event_registration_manage', args=[reg.access_token])).content.decode()
    assert SECRET in page and '4321' in page and 'Use your registered name.' in page
    # window closes well after the end
    Event.objects.filter(pk=e.pk).update(date=date.today() - timedelta(days=1))
    assert SECRET not in client.get(reverse('event_registration_manage', args=[reg.access_token])).content.decode()


def test_waitlisted_and_cancelled_never_get_the_link(client, clinic):
    e = make_event(max_participants=1)
    service.register(e, name='A One', phone='9000000001')
    w = service.register(e, name='B Two', phone='9000000002')
    soon = (timezone.now() + timedelta(minutes=5)).astimezone(e.tz)
    Event.objects.filter(pk=e.pk).update(date=soon.date(), start_time=soon.time().replace(microsecond=0),
                                         end_time=(soon + timedelta(hours=1)).time().replace(microsecond=0))
    assert SECRET not in client.get(reverse('event_registration_manage', args=[w.access_token])).content.decode()
    c = EventRegistration.objects.get(status='confirmed'); service.cancel_registration(c, by_staff=True)
    w.refresh_from_db(); assert w.status == 'confirmed'
    service.cancel_registration(w, by_staff=True)
    assert SECRET not in client.get(reverse('event_registration_manage', args=[w.access_token])).content.decode()


def test_registrant_ics_contains_manage_page_not_raw_link(client, clinic):
    e = make_event(description='Line1\nWith, comma; and semicolon')
    reg = service.register(e, name='A One', phone='9000000001')
    body = client.get(reverse('registration_ics', args=[reg.access_token])).content.decode().replace('\r\n ', '')
    assert 'BEGIN:VEVENT' in body and SECRET not in body
    assert reg.access_token in body
    pub = client.get(reverse('event_ics', args=[e.pk])).content.decode()
    assert 'With\\, comma\\; and semicolon' in pub.replace('\r\n ', '') and pub.endswith('\r\n')
    assert all(len(line.encode()) <= 75 for line in pub.split('\r\n'))


def test_unknown_token_404_and_feedback_gate(client, clinic):
    assert client.get(reverse('event_registration_manage', args=['nope'])).status_code == 404
    e = make_event(date=date.today() - timedelta(days=1), feedback_enabled=True)
    reg = EventRegistration.objects.create(event=e, name='A One', phone='9000000001', phone_key='9000000001')
    url = reverse('event_registration_manage', args=[reg.access_token])
    client.post(url, {'action': 'feedback', 'rating': '5', 'comment': 'Great'})
    fb = EventFeedback.objects.get()
    assert fb.registration == reg and fb.is_published is False and fb.reviewer_name == 'A One'
    client.post(url, {'action': 'feedback', 'rating': '1'})                       # second attempt ignored
    assert EventFeedback.objects.count() == 1
    other = EventRegistration.objects.create(event=e, name='W', phone='9', phone_key='9', status='waitlisted')
    client.post(reverse('event_registration_manage', args=[other.access_token]), {'action': 'feedback', 'rating': '5'})
    assert EventFeedback.objects.count() == 1                                      # waitlisted cannot review


def test_feedback_closed_until_event_completed(client, clinic):
    e = make_event(feedback_enabled=True)
    reg = service.register(e, name='A One', phone='9000000001')
    client.post(reverse('event_registration_manage', args=[reg.access_token]), {'action': 'feedback', 'rating': '5'})
    assert EventFeedback.objects.count() == 0


def test_old_name_leaking_feedback_endpoints_are_gone(client, clinic):
    e = make_event()
    from spinalcure.utils import encode_b64uuid
    base = f'/en/clinic/events/{encode_b64uuid(e.pk)}/'
    assert client.post(base + 'verify-registration/', data='{}', content_type='application/json').status_code == 404
    assert client.post(base + 'feedback/', data='{}', content_type='application/json').status_code == 404


def test_registrant_can_cancel_before_start_not_after(client, clinic):
    e = make_event(max_participants=1)
    a = service.register(e, name='A One', phone='9000000001', email='a@example.com')
    w = service.register(e, name='B Two', phone='9000000002', email='b@example.com')
    client.post(reverse('event_registration_manage', args=[a.access_token]), {'action': 'cancel'})
    a.refresh_from_db(); w.refresh_from_db()
    assert a.status == 'cancelled' and w.status == 'confirmed'
    Event.objects.filter(pk=e.pk).update(date=date.today() - timedelta(days=1))
    client.post(reverse('event_registration_manage', args=[w.access_token]), {'action': 'cancel'})
    w.refresh_from_db(); assert w.status == 'confirmed'


# ── cancellation / change notices / reminders ──────────────────────────────────────────────────

def test_cancel_event_notifies_everyone_once(clinic):
    e = make_event(max_participants=1)
    service.register(e, name='A One', phone='9000000001', email='a@example.com')
    service.register(e, name='B Two', phone='9000000002', email='b@example.com')
    service.register(e, name='C Three', phone='9000000003')                               # no email: nothing to send
    service.cancel_event(e, 'Speaker unwell'); service.cancel_event(e, 'again')
    assert Notification.objects.filter(event_type='event_cancelled').count() == 2
    e.refresh_from_db(); assert e.status == 'cancelled' and e.cancel_reason == 'Speaker unwell'
    with pytest.raises(service.EventError):
        service.register(e, name='D', phone='9000000004')


def test_schedule_change_notifies_once_per_distinct_change(clinic):
    e = make_event()
    service.register(e, name='A One', phone='9000000001', email='a@example.com')
    before = service.schedule_signature(e)
    e.start_time = time(14, 0); e.end_time = time(15, 0); e.save()
    assert service.announce_changes(e, before) == 1
    assert service.announce_changes(e, before) == 0                                # same change: deduped
    before2 = service.schedule_signature(e)
    e.title = 'Renamed only'; e.save()
    assert service.announce_changes(e, before2) == 0                               # non-schedule edit: silent
    e.venue = 'Room 5'; before3 = service.schedule_signature(e); e.save()
    assert service.announce_changes(e, 'different') == 1                           # a different change notifies again


def test_event_reminders_per_offset_deduped(clinic):
    e = make_event(reminder_offsets_minutes='60')
    service.register(e, name='A One', phone='9000000001', email='a@example.com')
    soon = (timezone.now() + timedelta(minutes=45)).astimezone(e.tz)
    Event.objects.filter(pk=e.pk).update(date=soon.date(), start_time=soon.time().replace(microsecond=0),
                                         end_time=(soon + timedelta(hours=1)).time().replace(microsecond=0))
    EventRegistration.objects.update(registered_at=timezone.now() - timedelta(days=2))
    call_command('send_reminders'); call_command('send_reminders')
    assert Notification.objects.filter(event_type='event_reminder').count() == 1


def test_attendance_only_for_confirmed(clinic):
    e = make_event(max_participants=1)
    a = service.register(e, name='A One', phone='9000000001')
    w = service.register(e, name='B Two', phone='9000000002')
    assert service.mark_attended(a).attended is True
    with pytest.raises(service.EventError):
        service.mark_attended(w)


# ── staff UI / API permissions ─────────────────────────────────────────────────────────────────

def test_staff_pages_require_capabilities(client, clinic):
    e = make_event()
    client.force_login(mk('staff'))
    for url in (reverse('event_list'), reverse('event_create'), reverse('event_registrations', args=[e.pk]),
                reverse('event_feedback_admin', args=[e.pk]), reverse('export_event_registrations_csv', args=[e.pk])):
        assert client.get(url).status_code == 302, url
    client.force_login(mk('receptionist'))
    assert client.get(reverse('event_registrations', args=[e.pk])).status_code == 200      # may see attendees
    assert client.get(reverse('event_list')).status_code == 302                              # but not manage events
    assert client.post(reverse('event_status', args=[e.pk]), {'action': 'cancel'}).status_code == 302
    e.refresh_from_db(); assert e.status == 'published'


def test_owner_creates_edits_publishes_and_cancels_via_ui(client, clinic):
    client.force_login(mk('owner'))
    day = (date.today() + timedelta(days=12)).isoformat()
    form = {'title': 'Posture Workshop', 'event_type': 'workshop', 'description': 'Hands-on', 'presenter': 'Dr Rao',
            'date': day, 'start_time': '10:00', 'end_time': '12:00', 'timezone': 'Asia/Kolkata', 'language': 'ta',
            'is_online': 'on', 'meeting_provider': 'zoom', 'meeting_link': 'https://zoom.example.com/j/1',
            'meeting_passcode': 'x1', 'max_participants': '20', 'waitlist_enabled': 'on', 'fees': '0',
            'reminder_offsets_minutes': '1440,60'}
    r = client.post(reverse('event_create'), form)
    assert r.status_code == 302, r.content[:2000]
    e = Event.objects.get(title='Posture Workshop')
    assert e.status == 'draft' and e.is_online and e.language == 'ta' and e.organizer.role == 'owner'
    assert reverse('event_detail', args=[e.pk]) not in client.get(reverse('public_event_list')).content.decode()  # draft hidden
    assert client.get(reverse('event_detail', args=[e.pk])).status_code == 404
    client.post(reverse('event_status', args=[e.pk]), {'action': 'publish'})
    e.refresh_from_db(); assert e.status == 'published'
    assert reverse('event_detail', args=[e.pk]) in client.get(reverse('public_event_list')).content.decode()
    # http meeting link rejected
    bad = client.post(reverse('event_create'), {**form, 'title': 'Bad', 'meeting_link': 'http://insecure.example.com'})
    assert bad.status_code == 200 and not Event.objects.filter(title='Bad').exists()
    # cancel -> notifies registrant
    service.register(e, name='A One', phone='9000000001', email='a@example.com')
    client.post(reverse('event_status', args=[e.pk]), {'action': 'cancel', 'reason': 'Rain'})
    e.refresh_from_db(); assert e.status == 'cancelled'
    assert Notification.objects.filter(event_type='event_cancelled').count() == 1
    # cannot delete an event that still has live registrations unless cancelled first: here cancelled -> allowed path
    assert client.get(reverse('event_list') + '?phase=cancelled').status_code == 200


def test_publishing_online_event_without_link_is_refused(client, clinic):
    e = make_event(status='draft', meeting_link='')
    client.force_login(mk('owner'))
    client.post(reverse('event_status', args=[e.pk]), {'action': 'publish'})
    e.refresh_from_db(); assert e.status == 'draft'


def test_list_filters_search_and_phase_tabs(client, clinic):
    make_event(title='Alpha Upcoming'); make_event(title='Beta Done', date=date.today() - timedelta(days=5))
    make_event(title='Gamma Cancelled', status='cancelled'); make_event(title='Delta Draft', status='draft')
    client.force_login(mk('owner'))
    def titles(q): return client.get(reverse('event_list') + q).content.decode()
    assert 'Alpha Upcoming' in titles('?phase=upcoming') and 'Beta Done' not in titles('?phase=upcoming')
    assert 'Beta Done' in titles('?phase=completed') and 'Gamma Cancelled' in titles('?phase=cancelled')
    assert 'Delta Draft' in titles('?phase=draft') and 'Delta Draft' not in titles('?phase=upcoming')
    assert 'Alpha Upcoming' in titles('?q=alpha') and 'Beta Done' not in titles('?q=alpha')
    # public tabs
    pub = lambda q: client.get(reverse('public_event_list') + q).content.decode()
    assert 'Alpha Upcoming' in pub('') and 'Delta Draft' not in pub('') and 'Beta Done' in pub('?phase=completed')
    assert 'Gamma Cancelled' in pub('?phase=cancelled')


def test_registration_admin_search_actions_and_exports_work(client, clinic):
    e = make_event(max_participants=1)
    a = service.register(e, name='Asha Raman', phone='9876543210', email='asha@example.com')
    w = service.register(e, name='Bala Kumar', phone='9000000002', email='bala@example.com')
    client.force_login(mk('receptionist'))
    page = client.get(reverse('event_registrations', args=[e.pk]), {'q': 'asha'}).content.decode()
    assert 'Asha Raman' in page and 'Bala Kumar' not in page                      # search used to 500 on full_name
    assert 'Bala Kumar' in client.get(reverse('event_registrations', args=[e.pk]), {'q': '9000000002'}).content.decode()
    assert 'Bala Kumar' in client.get(reverse('event_registrations', args=[e.pk]), {'status': 'waitlisted'}).content.decode()
    client.post(reverse('event_registration_action', args=[e.pk, a.pk]), {'action': 'attended'})
    a.refresh_from_db(); assert a.attended
    client.post(reverse('event_registration_action', args=[e.pk, w.pk]), {'action': 'promote'})
    w.refresh_from_db(); assert w.status == 'waitlisted'                           # full: refused
    client.post(reverse('event_registration_action', args=[e.pk, a.pk]), {'action': 'cancel'})
    w.refresh_from_db(); assert w.status == 'confirmed'                            # freed seat auto-promotes
    for kind in ('csv', 'excel', 'copy'):
        r = client.get(reverse(f'export_event_registrations_{kind}', args=[e.pk]))
        assert r.status_code == 200, kind                                          # exports used to crash on full_name
    assert b'Asha Raman' in client.get(reverse('export_event_registrations_csv', args=[e.pk])).content


def test_api_hides_private_fields_from_public_and_blocks_writes(clinic):
    e = make_event()
    anon = APIClient()
    data = anon.get('/api/events/').json()
    results = data['results'] if isinstance(data, dict) else data
    assert results and 'meeting_link' not in results[0] and 'meeting_passcode' not in results[0]
    assert anon.post('/api/events/', {}, format='json').status_code in (401, 403)
    staff = APIClient(); staff.force_authenticate(mk('staff'))
    assert staff.post('/api/events/', {}, format='json').status_code == 403
    owner = APIClient(); owner.force_authenticate(mk('owner'))
    d = owner.get(f'/api/events/{encode(e)}/').json()
    assert d['meeting_link'] == e.meeting_link                                      # managers do see it
