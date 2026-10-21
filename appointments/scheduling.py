"""
Scheduling engine: slot generation, validation and state changes.

All clock times are the clinic's local time (settings.TIME_ZONE). Appointments store a local date and
time; this module converts to aware datetimes for every comparison so DST/UTC offsets never leak into
the stored data.

Every write path (staff UI, API, public form, self-service link) goes through book() /
reschedule() so the same rules apply everywhere:
  * the slot must exist in the practitioner's shifts and not be on leave/holiday,
  * it must not overlap (with buffer) another live appointment,
  * notice / advance limits apply to public bookings,
  * the check is repeated inside a transaction holding a lock on the practitioner row, so two
    simultaneous requests for the same slot cannot both succeed.
"""
from django.utils.translation import gettext
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from clinic.models import Practitioner
from notifications.service import notify, notify_staff
from patients.models import Patient

from .models import Appointment, BookingSettings, DoctorAvailability, TimeOff

logger = logging.getLogger(__name__)


class SchedulingError(Exception):
    """Raised for any rule violation. `code` is stable for clients/tests; `message` is user-facing."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class Slot:
    start: datetime          # aware, clinic timezone
    end: datetime
    practitioner_id: object

    @property
    def time(self):
        return self.start.timetz().replace(tzinfo=None)

    @property
    def label(self):
        return self.start.strftime('%H:%M')


def _tz():
    return timezone.get_default_timezone()


def _aware(day, t):
    return timezone.make_aware(datetime.combine(day, t), _tz())


def _now(now=None):
    return now or timezone.now()


def _overlaps(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end


# ── inputs to the generator ────────────────────────────────────────────────────────────────────

def shifts_for(practitioner, day, appointment_type):
    qs = DoctorAvailability.objects.filter(
        practitioner=practitioner, day_of_week=day.weekday(), is_available=True)
    types = ('both', appointment_type)
    return [s for s in qs.filter(appointment_type__in=types).order_by('start_time')
            if (not s.valid_from or s.valid_from <= day) and (not s.valid_until or day <= s.valid_until)]


def blocked_intervals(practitioner, day):
    """Aware (start, end) intervals when nobody can be booked; a full-day block spans the whole day."""
    out = []
    qs = TimeOff.objects.filter(start_date__lte=day, end_date__gte=day)
    qs = qs.filter(practitioner=practitioner) | qs.filter(practitioner__isnull=True)
    for off in qs:
        start = off.start_time if off.start_time and off.start_date == day else time.min
        end = off.end_time if off.end_time and off.end_date == day else time.max
        out.append((_aware(day, start), _aware(day, end.replace(microsecond=0)) if end != time.max
                    else _aware(day, time.min) + timedelta(days=1)))
    return out


def live_appointments(practitioner, day, exclude=None):
    qs = Appointment.objects.filter(
        practitioner=practitioner, appointment_date=day, status__in=Appointment.OCCUPYING)
    if exclude is not None:
        qs = qs.exclude(pk=getattr(exclude, 'pk', exclude))
    return list(qs)


# ── slot generation ────────────────────────────────────────────────────────────────────────────

def generate_slots(practitioner, day, appointment_type='physical', duration=None, exclude=None,
                   now=None, enforce_notice=True, enforce_hours=True):
    """All bookable Slots for one practitioner on one local date."""
    cfg = BookingSettings.get()
    now = _now(now)
    today = timezone.localtime(now, _tz()).date()
    if day < today or (enforce_notice and day > today + timedelta(days=cfg.max_advance_days)):
        return []
    if not getattr(practitioner, 'is_active', True):
        return []

    blocked = blocked_intervals(practitioner, day)
    existing = [(a.starts_at, a.ends_at) for a in live_appointments(practitioner, day, exclude)]
    earliest = now + timedelta(minutes=cfg.min_notice_minutes) if enforce_notice else now

    slots, seen = [], set()
    for shift in shifts_for(practitioner, day, appointment_type):
        length = timedelta(minutes=duration or shift.slot_duration_minutes)
        step = timedelta(minutes=shift.slot_duration_minutes)
        buf = timedelta(minutes=shift.buffer_minutes)
        shift_end = _aware(day, shift.end_time)
        brk = (_aware(day, shift.break_start), _aware(day, shift.break_end)) if shift.break_start else None
        in_shift = sum(1 for (s, e) in existing if _aware(day, shift.start_time) <= s < shift_end)
        cursor = _aware(day, shift.start_time)
        while cursor + length <= shift_end:
            start, end = cursor, cursor + length
            cursor += step
            if shift.max_appointments is not None and in_shift >= shift.max_appointments:
                break
            if start in seen or start < earliest:
                continue
            if brk and _overlaps(start, end, *brk):
                continue
            if any(_overlaps(start, end, b0, b1) for (b0, b1) in blocked):
                continue
            if any(_overlaps(start - buf, end + buf, e0, e1) for (e0, e1) in existing):
                continue
            seen.add(start)
            slots.append(Slot(start, end, practitioner.pk))
    return sorted(slots, key=lambda s: s.start)


def _diagnose(practitioner, day, start_dt, end_dt, appointment_type, exclude, now, cfg, enforce_notice):
    """Most specific reason a requested slot is not bookable."""
    today = timezone.localtime(now, _tz()).date()
    if start_dt < now:
        return SchedulingError('past', gettext('That time is in the past.'))
    if enforce_notice and start_dt < now + timedelta(minutes=cfg.min_notice_minutes):
        return SchedulingError('too_soon', gettext('Bookings need at least %(min_notice_minutes)s minutes notice.') % {'min_notice_minutes': cfg.min_notice_minutes})
    if enforce_notice and day > today + timedelta(days=cfg.max_advance_days):
        return SchedulingError('too_far', gettext('Bookings open up to %(max_advance_days)s days ahead.') % {'max_advance_days': cfg.max_advance_days})
    if any(_overlaps(start_dt, end_dt, b0, b1) for (b0, b1) in blocked_intervals(practitioner, day)):
        return SchedulingError('blocked', gettext('The practitioner is not available on that date (leave or closure).'))
    shifts = shifts_for(practitioner, day, appointment_type)
    if not shifts:
        return SchedulingError('closed', gettext('The practitioner does not work on that day.'))
    inside = [s for s in shifts if _aware(day, s.start_time) <= start_dt and end_dt <= _aware(day, s.end_time)]
    if not inside:
        return SchedulingError('outside_hours', gettext('That time is outside working hours.'))
    if any(s.break_start and _overlaps(start_dt, end_dt, _aware(day, s.break_start), _aware(day, s.break_end))
           for s in inside):
        return SchedulingError('outside_hours', gettext('That time falls in a break.'))
    if any(_overlaps(start_dt, end_dt, a.starts_at, a.ends_at) for a in live_appointments(practitioner, day, exclude)):
        return SchedulingError('conflict', gettext('That slot has just been taken. Please choose another time.'))
    return SchedulingError('unavailable', gettext('That slot is not available.'))


def validate_slot(practitioner, day, start_time, appointment_type='physical', duration=None, exclude=None,
                  now=None, enforce_notice=True, enforce_hours=True):
    """Return the matching Slot or raise SchedulingError. Reads fresh data every call."""
    if practitioner is None:
        raise SchedulingError('no_practitioner', gettext('Choose a practitioner.'))
    cfg, now = BookingSettings.get(), _now(now)
    if start_time is None or day is None:
        raise SchedulingError('invalid_time', gettext('Choose a date and time.'))
    if duration is not None and not (5 <= duration <= 480):
        raise SchedulingError('invalid_time', gettext('Duration must be between 5 and 480 minutes.'))
    start_dt = _aware(day, start_time)
    length = timedelta(minutes=duration or cfg.default_duration_minutes)

    if enforce_hours:
        for slot in generate_slots(practitioner, day, appointment_type, duration, exclude, now, enforce_notice):
            if slot.start == start_dt:
                return slot
        raise _diagnose(practitioner, day, start_dt, start_dt + length, appointment_type, exclude, now, cfg,
                        enforce_notice)

    # Staff override of working hours (walk-ins): still no past times, leave/closure or double booking.
    end_dt = start_dt + length
    if start_dt < now - timedelta(minutes=5):
        raise SchedulingError('past', gettext('That time is in the past.'))
    if any(_overlaps(start_dt, end_dt, b0, b1) for (b0, b1) in blocked_intervals(practitioner, day)):
        raise SchedulingError('blocked', gettext('The practitioner is not available on that date (leave or closure).'))
    if any(_overlaps(start_dt, end_dt, a.starts_at, a.ends_at) for a in live_appointments(practitioner, day, exclude)):
        raise SchedulingError('conflict', gettext('That slot has just been taken. Please choose another time.'))
    return Slot(start_dt, end_dt, practitioner.pk)


_ERROR_PRIORITY = ['past', 'too_soon', 'too_far', 'conflict', 'blocked', 'outside_hours', 'closed', 'unavailable']


def pick_practitioner(day, start_time, appointment_type='physical', duration=None, now=None):
    """
    First active practitioner who can take this slot (for "any available doctor").
    Raises the most informative SchedulingError when nobody can.
    """
    errors = []
    for practitioner in Practitioner.objects.filter(is_active=True).order_by('name'):
        try:
            validate_slot(practitioner, day, start_time, appointment_type, duration, now=now)
            return practitioner
        except SchedulingError as exc:
            errors.append(exc)
    if not errors:
        raise SchedulingError('unavailable', gettext('No practitioner is available at that time.'))
    raise min(errors, key=lambda e: _ERROR_PRIORITY.index(e.code) if e.code in _ERROR_PRIORITY else 99)


# ── writes ─────────────────────────────────────────────────────────────────────────────────────

def _lock(practitioner):
    """Serialise bookings per practitioner (row lock on MySQL/Postgres; SQLite serialises writers)."""
    return Practitioner.objects.select_for_update().get(pk=practitioner.pk)


def _contact_filters(patient, guest_phone, guest_email):
    from django.db.models import Q
    q = Q()
    if patient is not None:
        q |= Q(patient=patient)
    if guest_phone:
        q |= Q(guest_phone=guest_phone)
    if guest_email:
        q |= Q(guest_email__iexact=guest_email)
    return q


def book(*, practitioner=None, day, start_time, appointment_type='physical', duration=None, patient=None,
         guest_name='', guest_phone='', guest_email='', reason='', source='staff', actor=None,
         request_key=None, ignore_notice=False, ignore_hours=False, status='scheduled', now=None):
    """Create an appointment. Raises SchedulingError; never leaves a half-created booking."""
    cfg, now = BookingSettings.get(), _now(now)
    if patient is None and not (guest_name and (guest_phone or guest_email)):
        raise SchedulingError('invalid_contact', gettext('A patient, or a name and phone/email, is required.'))
    if source == 'public' and not cfg.allow_public_booking:
        raise SchedulingError('closed', gettext('Online booking is currently unavailable. Please call the clinic.'))
    if request_key:
        prior = Appointment.objects.filter(request_key=request_key).first()
        if prior:
            return prior                                  # retried request: same booking, no duplicate
    if practitioner is None:
        practitioner = pick_practitioner(day, start_time, appointment_type, duration, now)
    duration = duration or None
    enforce_notice = not (ignore_notice and source == 'staff')
    enforce_hours = not (ignore_hours and source == 'staff')
    try:
        with transaction.atomic():
            _lock(practitioner)
            slot = validate_slot(practitioner, day, start_time, appointment_type, duration, None, now,
                                 enforce_notice, enforce_hours)
            if source in ('public', 'portal'):
                upcoming = Appointment.objects.filter(
                    _contact_filters(patient, guest_phone, guest_email),
                    status__in=('scheduled', 'confirmed'), appointment_date__gte=timezone.localtime(now, _tz()).date()).count()
                if upcoming >= cfg.max_active_per_contact:
                    raise SchedulingError('limit', gettext('You already have the maximum number of upcoming appointments.'))
            appt = Appointment.objects.create(
                patient=patient, practitioner=practitioner, appointment_date=day,
                appointment_time=slot.time, duration_minutes=int((slot.end - slot.start).total_seconds() // 60),
                appointment_type=appointment_type, status=status, reason=reason[:300], booked_via=source,
                guest_name=guest_name if patient is None else None,
                guest_phone=guest_phone if patient is None else None,
                guest_email=guest_email if patient is None else None,
                request_key=request_key or None,
                confirmed_at=now if status == 'confirmed' else None)
    except IntegrityError:
        # The unique constraint caught a same-start race that slipped past the lock.
        raise SchedulingError('conflict', gettext('That slot has just been taken. Please choose another time.'))
    _announce_booked(appt, actor)
    return appt


def _manage_path(appt):
    return reverse('appointment_manage', args=[appt.manage_token])


def _recipient(appt):
    return {'patient': appt.patient} if appt.patient_id else {'email': appt.guest_email or ''}


def _ctx(appt):
    return {
        'practitioner': appt.practitioner.name if appt.practitioner_id else '',
        'clinic': _clinic_name(), 'date': appt.appointment_date, 'time': appt.appointment_time,
        'who': appt.display_name,
    }


def _clinic_name():
    from clinic.models import ClinicProfile
    c = ClinicProfile.objects.first()
    return c.name if c else 'SpinalCure'


def _safely(fn, *args, **kwargs):
    """Notifications are best-effort: a failure here must never undo or hide a successful booking."""
    try:
        return fn(*args, **kwargs)
    except Exception:
        logger.exception('Appointment notification failed')
        return None


def _announce_booked(appt, actor):
    rcpt = _recipient(appt)
    if rcpt.get('patient') or rcpt.get('email'):
        _safely(lambda: notify('appointment_booked', context=_ctx(appt), url=_manage_path(appt),
                               dedupe_key=f'appt:{appt.pk}:booked', **rcpt))
    def clinic_inbox():
        from clinic.models import ClinicProfile
        c = ClinicProfile.objects.first()
        if c and c.email:
            notify('appointment_booked_clinic', email=c.email, context=_ctx(appt), url=reverse('appointment_calendar'),
                   dedupe_key=f'appt:{appt.pk}:booked_clinic')
    _safely(clinic_inbox)
    _safely(lambda: notify_staff('appointment_booked_staff', 'appointments.manage', context=_ctx(appt),
                                 url=reverse('appointment_calendar'), dedupe_key=f'appt:{appt.pk}:booked_staff'))


def confirm(appt, actor=None):
    return _transition(appt, 'confirmed', actor)


def complete(appt, actor=None):
    if appt.starts_at > timezone.now():
        raise SchedulingError('too_early', gettext('An appointment cannot be completed before it starts.'))
    return _transition(appt, 'completed', actor)


def mark_no_show(appt, actor=None):
    if appt.starts_at > timezone.now():
        raise SchedulingError('too_early', gettext('An appointment cannot be a no-show before it starts.'))
    appt = _transition(appt, 'no_show', actor)
    if appt.patient_id or appt.guest_email:
        _safely(lambda: notify('appointment_missed', context=_ctx(appt), url=_manage_path(appt),
                               dedupe_key=f'appt:{appt.pk}:missed', **_recipient(appt)))
    return appt


def _transition(appt, new_status, actor=None, **extra):
    with transaction.atomic():
        fresh = Appointment.objects.select_for_update().get(pk=appt.pk)
        if not fresh.can_transition(new_status):
            raise SchedulingError('invalid_transition', gettext('A %(value1)s appointment cannot become %(value3)s.') % {'value1': fresh.status.replace("_", " "), 'value3': new_status.replace("_", " ")})
        fresh.status = new_status
        if new_status == 'confirmed':
            fresh.confirmed_at = timezone.now()
        for k, v in extra.items():
            setattr(fresh, k, v)
        fresh.save()
    if new_status == 'confirmed' and (fresh.patient_id or fresh.guest_email):
        _safely(lambda: notify('appointment_confirmed', context=_ctx(fresh), url=_manage_path(fresh),
                               dedupe_key=f'appt:{fresh.pk}:confirmed', **_recipient(fresh)))
    return fresh


def cancel(appt, actor=None, reason='', by_patient=False, now=None):
    now = _now(now)
    cfg = BookingSettings.get()
    if by_patient and appt.starts_at - now < timedelta(hours=cfg.cancel_cutoff_hours):
        raise SchedulingError('too_late', gettext('Appointments can only be cancelled online up to %(cancel_cutoff_hours)s hours before. Please call the clinic.') % {'cancel_cutoff_hours': cfg.cancel_cutoff_hours})
    appt = _transition(appt, 'cancelled', actor, cancelled_at=now, cancel_reason=(reason or '')[:300],
                       cancelled_by=actor if getattr(actor, 'is_authenticated', False) else None)
    if appt.patient_id or appt.guest_email:
        _safely(lambda: notify('appointment_cancelled', context=_ctx(appt),
                               dedupe_key=f'appt:{appt.pk}:cancelled', **_recipient(appt)))
    return appt


def reschedule(appt, *, day, start_time, practitioner=None, actor=None, by_patient=False, source=None,
               ignore_notice=False, ignore_hours=False, now=None):
    """Move an appointment: the old row becomes 'rescheduled' and a new linked row is created, atomically."""
    now = _now(now)
    cfg = BookingSettings.get()
    if by_patient and appt.starts_at - now < timedelta(hours=cfg.cancel_cutoff_hours):
        raise SchedulingError('too_late', gettext('Appointments can only be changed online up to %(cancel_cutoff_hours)s hours before. Please call the clinic.') % {'cancel_cutoff_hours': cfg.cancel_cutoff_hours})
    practitioner = practitioner or appt.practitioner
    if practitioner is None:
        practitioner = pick_practitioner(day, start_time, appt.appointment_type, appt.duration_minutes, now)
    source = source or ('public' if by_patient else 'staff')
    enforce_notice = not (ignore_notice and not by_patient)
    enforce_hours = not (ignore_hours and not by_patient)
    try:
        with transaction.atomic():
            _lock(practitioner)
            old = Appointment.objects.select_for_update().get(pk=appt.pk)
            if not old.can_transition('rescheduled'):
                raise SchedulingError('invalid_transition', gettext('This appointment can no longer be rescheduled.'))
            slot = validate_slot(practitioner, day, start_time, old.appointment_type, old.duration_minutes,
                                 exclude=old, now=now, enforce_notice=enforce_notice, enforce_hours=enforce_hours)
            old.status = 'rescheduled'
            old.save(update_fields=['status', 'updated_at'])
            new = Appointment.objects.create(
                patient=old.patient, guest_name=old.guest_name, guest_phone=old.guest_phone,
                guest_email=old.guest_email, practitioner=practitioner, appointment_date=day,
                appointment_time=slot.time, duration_minutes=old.duration_minutes,
                appointment_type=old.appointment_type, status='scheduled', reason=old.reason, notes=old.notes,
                booked_via=old.booked_via, rescheduled_from=old)
    except IntegrityError:
        raise SchedulingError('conflict', gettext('That slot has just been taken. Please choose another time.'))
    if new.patient_id or new.guest_email:
        _safely(lambda: notify('appointment_rescheduled', context=_ctx(new), url=_manage_path(new),
                               dedupe_key=f'appt:{new.pk}:rescheduled', **_recipient(new)))
    return new
