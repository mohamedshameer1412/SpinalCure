"""
Event lifecycle rules. Every path (public form, staff UI, API) goes through here so capacity, deadlines,
waitlist order, status and meeting-link access cannot drift apart.
"""
import hashlib
import logging
import re
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from notifications.service import notify

from .models import Event, EventRegistration

logger = logging.getLogger(__name__)

JOIN_OPENS_BEFORE = timedelta(minutes=30)     # meeting link becomes visible this long before start...
JOIN_STAYS_OPEN_AFTER = timedelta(hours=1)    # ...and for this long after the scheduled end


class EventError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def phone_key(phone):
    digits = re.sub(r'\D', '', phone or '')
    return digits[-10:] if len(digits) >= 10 else digits


def _safely(fn):
    try:
        return fn()
    except Exception:
        logger.exception('Event notification failed')
        return None


def manage_path(reg):
    return reverse('event_registration_manage', args=[reg.access_token])


def _ctx(event):
    return {'event': event.title, 'date': event.date, 'time': event.start_time}


def _notify_reg(kind, reg, key_suffix=''):
    """Notify a registrant by email if they gave one. Best effort; dedupe per registration+kind."""
    if not reg.email:
        return None
    n = _safely(lambda: notify(kind, email=reg.email, context=_ctx(reg.event), url=manage_path(reg),
                               dedupe_key=f'event:{reg.event_id}:{reg.pk}:{kind}{key_suffix}'))
    return n if n is not None and getattr(n, 'was_created', False) else None   # None = nothing new was sent


# ── registration ───────────────────────────────────────────────────────────────────────────────

def register(event, *, name, phone, email='', notes='', language='en', now=None):
    """Create a confirmed or waitlisted registration atomically. Raises EventError."""
    now = now or timezone.now()
    key = phone_key(phone)
    if len(key) < 7:
        raise EventError('invalid_phone', 'Please enter a valid phone number.')
    with transaction.atomic():
        ev = Event.objects.select_for_update().get(pk=event.pk)      # serialises concurrent sign-ups
        if ev.status != 'published':
            raise EventError('closed', 'Registration is not open for this event.')
        if ev.phase in ('completed', 'cancelled'):
            raise EventError('ended', 'This event has already ended.')
        if ev.registration_deadline and now > ev.registration_deadline:
            raise EventError('deadline', 'Registration for this event has closed.')
        dup = Q(phone_key=key)
        if email:
            dup |= Q(email__iexact=email)
        if ev.registrations.filter(dup, status__in=('confirmed', 'waitlisted')).exists():
            raise EventError('duplicate', 'You are already registered for this event. Check your email for the link.')
        if ev.max_participants is None or ev.confirmed_count < ev.max_participants:
            status = 'confirmed'
        elif ev.waitlist_enabled:
            status = 'waitlisted'
        else:
            raise EventError('full', 'This event is full.')
        reg = EventRegistration.objects.create(
            event=ev, name=name, phone=phone, phone_key=key, email=email, notes=notes, status=status,
            language=language)
    _notify_reg('event_registered' if status == 'confirmed' else 'event_waitlisted', reg)
    return reg


def cancel_registration(reg, by_staff=False):
    with transaction.atomic():
        ev = Event.objects.select_for_update().get(pk=reg.event_id)
        reg = EventRegistration.objects.select_for_update().get(pk=reg.pk)
        if reg.status == 'cancelled':
            return reg
        if not by_staff and ev.phase in ('live', 'completed'):
            raise EventError('started', 'This event has already started, so it can no longer be cancelled online.')
        was_confirmed = reg.status == 'confirmed'
        reg.status, reg.cancelled_at = 'cancelled', timezone.now()
        reg.save(update_fields=['status', 'cancelled_at'])
    if was_confirmed:
        promote_waitlist(ev)
    return reg


def promote_waitlist(event):
    """Move waitlisted people into freed seats, oldest first. Returns the promoted registrations."""
    promoted = []
    with transaction.atomic():
        ev = Event.objects.select_for_update().get(pk=event.pk)
        if ev.status != 'published' or ev.phase in ('completed', 'cancelled'):
            return promoted
        waiting = ev.registrations.select_for_update().filter(status='waitlisted').order_by('registered_at')
        for reg in waiting:
            if ev.max_participants is not None and ev.confirmed_count >= ev.max_participants:
                break
            reg.status, reg.promoted_at = 'confirmed', timezone.now()
            reg.save(update_fields=['status', 'promoted_at'])
            promoted.append(reg)
    for reg in promoted:
        _notify_reg('event_promoted', reg)
    return promoted


def mark_attended(reg, attended=True):
    if reg.status != 'confirmed':
        raise EventError('not_confirmed', 'Only confirmed registrations can be marked as attended.')
    reg.attended = attended
    reg.attended_at = timezone.now() if attended else None
    reg.save(update_fields=['attended', 'attended_at'])
    return reg


# ── lifecycle ──────────────────────────────────────────────────────────────────────────────────

def publish(event):
    event.status = 'published'
    event.full_clean()
    event.save()
    promote_waitlist(event)
    return event


def unpublish(event):
    if event.status == 'published':
        event.status = 'draft'
        event.save()
    return event


def archive(event):
    if event.status == 'published' and event.phase in ('upcoming', 'live'):
        raise EventError('active', 'Cancel or unpublish an upcoming event before archiving it.')
    event.status = 'archived'
    event.save()
    return event


def cancel_event(event, reason=''):
    if event.status == 'cancelled':
        return event
    event.status, event.cancel_reason = 'cancelled', (reason or '')[:300]
    event.save()
    for reg in event.registrations.filter(status__in=('confirmed', 'waitlisted')):
        _notify_reg('event_cancelled', reg)
    return event


SCHEDULE_FIELDS = ('date', 'start_time', 'end_time', 'venue', 'is_online', 'meeting_link', 'timezone')


def schedule_signature(event):
    raw = '|'.join(str(getattr(event, f)) for f in SCHEDULE_FIELDS)
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def announce_changes(event, before_signature):
    """Tell registrants when the schedule/venue/link changed on a published event (once per distinct change)."""
    after = schedule_signature(event)
    if event.status != 'published' or after == before_signature:
        return 0
    count = 0
    for reg in event.registrations.filter(status__in=('confirmed', 'waitlisted')):
        if _notify_reg('event_changed', reg, key_suffix=f':{after}'):
            count += 1
    return count


# ── meeting access ─────────────────────────────────────────────────────────────────────────────

def join_info(reg, now=None):
    """What a registrant may see about joining. The link is only revealed to confirmed registrants in the window."""
    now = now or timezone.now()
    ev = reg.event
    info = {'online': ev.is_online, 'open': False, 'opens_at': None, 'link': '', 'passcode': '', 'instructions': ''}
    if not ev.is_online or reg.status != 'confirmed' or ev.status != 'published':
        return info
    opens = ev.starts_at - JOIN_OPENS_BEFORE
    closes = ev.ends_at + JOIN_STAYS_OPEN_AFTER
    info['opens_at'] = opens
    info['instructions'] = ev.access_instructions
    if opens <= now <= closes and ev.meeting_link:
        info.update(open=True, link=ev.meeting_link, passcode=ev.meeting_passcode)
    return info


# ── calendar file ──────────────────────────────────────────────────────────────────────────────

def _ics_escape(text):
    """RFC 5545 TEXT escaping: backslash, semicolon, comma and newlines."""
    text = (text or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
    return text.replace('\r\n', '\n').replace('\r', '').replace('\n', '\\n')


def build_ics(event, base_url='', link=''):
    """RFC 5545 calendar entry in UTC. The meeting link is included only when the caller is authorised."""
    from datetime import timezone as dt_tz
    fmt = '%Y%m%dT%H%M%SZ'
    start, end = event.starts_at.astimezone(dt_tz.utc), event.ends_at.astimezone(dt_tz.utc)
    desc = strip_tags(event.description or '')
    if link:
        desc += f'\nJoin: {link}'
        if event.meeting_passcode:
            desc += f'\nPasscode: {event.meeting_passcode}'
    location = 'Online' if event.is_online else event.venue
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//SpinalCure//Events//EN', 'CALSCALE:GREGORIAN',
             'METHOD:PUBLISH', 'BEGIN:VEVENT', f'UID:{event.pk}@spinalcure',
             f'DTSTAMP:{timezone.now().astimezone(dt_tz.utc).strftime(fmt)}',
             f'DTSTART:{start.strftime(fmt)}', f'DTEND:{end.strftime(fmt)}',
             f'SUMMARY:{_ics_escape(event.title)}', f'DESCRIPTION:{_ics_escape(desc)}',
             f'LOCATION:{_ics_escape(location)}',
             f'STATUS:{"CANCELLED" if event.status == "cancelled" else "CONFIRMED"}']
    if base_url:
        lines.append(f'URL:{base_url}')
    lines += ['END:VEVENT', 'END:VCALENDAR']
    # fold lines longer than 75 octets
    out = []
    for line in lines:
        while len(line.encode()) > 75:
            cut = 75
            while len(line[:cut].encode()) > 75:
                cut -= 1
            out.append(line[:cut]); line = ' ' + line[cut:]
        out.append(line)
    return '\r\n'.join(out) + '\r\n'
