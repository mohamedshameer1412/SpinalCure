"""
Event registration rules in one place: capacity, waitlist, deadlines, duplicates,
cancellation with waitlist promotion, private join links and notifications.
"""
from datetime import timezone as dt_timezone

from django.db import transaction
from django.urls import reverse
from django.utils import formats

from notifications.services import notify_users, queue_email, users_with_perm
from .models import Event, EventRegistration


class RegistrationError(Exception):
    pass


def _when(event):
    return f"{formats.date_format(event.date, 'D, d M Y')}, {event.start_time:%I:%M %p}–{event.end_time:%I:%M %p} IST"


def manage_url(request, reg):
    return request.build_absolute_uri(reverse('event_registration_manage', args=[reg.access_token]))


def _email_status(request, reg, subject_prefix='Registration'):
    e = reg.event
    where = 'Online (the join link is on your registration page)' if e.is_online else e.venue
    if reg.status == 'confirmed':
        head = f'You are registered for "{e.title}".'
    elif reg.status == 'waitlisted':
        head = f'"{e.title}" is full, so you are on the waitlist. We will email you if a seat opens.'
    else:
        head = f'Your registration for "{e.title}" is cancelled.'
    text = (f'{head}\n\nWhen: {_when(e)}\nWhere: {where}\n\n'
            f'View or cancel your registration: {manage_url(request, reg)}')
    queue_email(reg.email, 'event_registration', f'{subject_prefix}: {e.title}', text,
                dedupe_key=f'evreg:{reg.pk}:{reg.status}:{subject_prefix}')


def register(request, event_id, name, phone, email, notes=''):
    """Returns the registration (confirmed or waitlisted). Raises RegistrationError with a user message."""
    with transaction.atomic():
        event = Event.objects.select_for_update().get(pk=event_id)  # serialises capacity checks
        reason = event.registration_closed_reason()
        if reason:
            raise RegistrationError(reason)
        if event.registrations.filter(phone=phone).exclude(status='cancelled').exists():
            raise RegistrationError('This phone number is already registered for this event.')
        full = event.max_participants and event.confirmed_count >= event.max_participants
        if full and not event.waitlist_enabled:
            raise RegistrationError('This event is full.')
        reg = EventRegistration.objects.create(event=event, name=name, phone=phone, email=email, notes=notes,
                                               status='waitlisted' if full else 'confirmed')
    _email_status(request, reg)
    notify_users([u for u in users_with_perm('events_manage')], 'event_registration',
                 f'New {"waitlist " if reg.status == "waitlisted" else ""}registration: {event.title}',
                 f'{name} · {event.confirmed_count}{"/" + str(event.max_participants) if event.max_participants else ""} confirmed',
                 reverse('event_registrations', args=[event.pk]), email=False)
    return reg


def cancel(request, reg):
    """Cancel a registration and move the first waitlisted person up if a seat opened."""
    with transaction.atomic():
        event = Event.objects.select_for_update().get(pk=reg.event_id)
        reg.refresh_from_db()
        if reg.status == 'cancelled':
            return None
        was_confirmed = reg.status == 'confirmed'
        reg.status = 'cancelled'
        reg.save(update_fields=['status'])
        promoted = None
        if was_confirmed and event.phase == 'upcoming':
            promoted = event.registrations.filter(status='waitlisted').order_by('registered_at').first()
            if promoted:
                promoted.status = 'confirmed'
                promoted.save(update_fields=['status'])
    _email_status(request, reg)
    if promoted:
        _email_status(request, promoted, subject_prefix='A seat opened up')
    return promoted


def notify_change(request, event, what):
    """Email everyone still registered that the event changed or was cancelled."""
    regs = event.registrations.exclude(status='cancelled').exclude(email='')
    stamp = f'{event.date}:{event.start_time}:{event.is_cancelled}:{event.venue}:{event.is_online}'
    for reg in regs:
        if event.is_cancelled:
            text = f'"{event.title}" on {_when(event)} has been cancelled.'
            if event.cancel_reason:
                text += f'\nReason: {event.cancel_reason}'
        else:
            text = f'"{event.title}" has changed ({what}).\nNow: {_when(event)}\nWhere: {"Online" if event.is_online else event.venue}'
        text += f'\n\nYour registration: {manage_url(request, reg)}'
        queue_email(reg.email, 'event_changed', f'{"Cancelled" if event.is_cancelled else "Updated"}: {event.title}', text,
                    dedupe_key=f'evchange:{reg.pk}:{stamp}')
    return regs.count()


def ics(event, url):
    """Calendar file. No meeting link inside: calendars are often shared."""
    def fmt(dt):
        return dt.astimezone(dt_timezone.utc).strftime('%Y%m%dT%H%M%SZ')

    def esc(v):
        return str(v).replace('\\', '\\\\').replace(';', '\;').replace(',', '\\,').replace('\n', '\\n')
    return '\r\n'.join([
        'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//SpinalCure//Events//EN', 'BEGIN:VEVENT',
        f'UID:event-{event.pk}@spinalcure', f'DTSTAMP:{fmt(event.starts_at)}',
        f'DTSTART:{fmt(event.starts_at)}', f'DTEND:{fmt(event.ends_at)}',
        f'SUMMARY:{esc(event.title)}', f'LOCATION:{esc("Online" if event.is_online else event.venue)}',
        f'DESCRIPTION:{esc(url)}', f'STATUS:{"CANCELLED" if event.is_cancelled else "CONFIRMED"}',
        'END:VEVENT', 'END:VCALENDAR', '',
    ])
