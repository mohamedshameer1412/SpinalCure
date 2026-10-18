"""
Appointment slot engine: one place that decides what can be booked.

Sources, in order:
  1. Leave / clinic holidays (PractitionerLeave) close the day.
  2. A practitioner with any DoctorAvailability rows uses those weekly shifts.
  3. A practitioner with no rows (or no practitioner chosen and no rows in the clinic)
     falls back to the clinic's default hours below.

All times are clinic-local (settings.TIME_ZONE). Every booking path calls
`check_bookable` inside `booking_lock`, so the server re-validates what the UI showed.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, time

from django.db import connection
from django.db.models import Q
from django.utils import timezone

from .models import Appointment, DoctorAvailability, PractitionerLeave


@dataclass
class Shift:
    start: time
    end: time
    step: int            # minutes between slot starts
    length: int          # default appointment length
    buffer: int = 0      # minutes kept free after each appointment
    max_appointments: int = None


# Clinic default hours, used until availability is configured. Monday=0 ... Sunday=6 (closed).
DEFAULT_PHYSICAL = {d: [(time(10), time(13)), (time(17, 30), time(20, 30))] for d in (0, 1, 2, 3, 5)}
DEFAULT_PHYSICAL[4] = [(time(18, 30), time(20, 30))]
DEFAULT_ONLINE = {d: [(time(9), time(17))] for d in range(6)}
DEFAULT_STEP = 15
DEFAULT_DURATION = 30


class BookingError(Exception):
    pass


def _minutes(t):
    return t.hour * 60 + t.minute


def _on_leave(practitioner, day):
    q = Q(practitioner__isnull=True)
    if practitioner:
        q |= Q(practitioner=practitioner)
    return PractitionerLeave.objects.filter(q, start_date__lte=day, end_date__gte=day).exists()


def shifts_for(practitioner, day, appointment_type='physical'):
    if _on_leave(practitioner, day):
        return []
    rows = DoctorAvailability.objects.filter(is_available=True, day_of_week=day.weekday())
    if practitioner:
        configured = DoctorAvailability.objects.filter(practitioner=practitioner).exists()
        rows = rows.filter(practitioner=practitioner)
    else:
        configured = DoctorAvailability.objects.filter(practitioner__is_active=True).exists()
        rows = rows.filter(practitioner__is_active=True)
    if configured:
        return [Shift(r.start_time, r.end_time, r.slot_duration_minutes, r.slot_duration_minutes, r.buffer_minutes, r.max_appointments) for r in rows]
    defaults = DEFAULT_ONLINE if appointment_type == 'online' else DEFAULT_PHYSICAL
    return [Shift(s, e, DEFAULT_STEP, DEFAULT_DURATION) for s, e in defaults.get(day.weekday(), [])]


def _booked(practitioner, day, exclude_id=None):
    """(start_min, end_min) of appointments that hold time. No practitioner = clinic-wide, as before."""
    qs = Appointment.objects.filter(appointment_date=day, status__in=Appointment.ACTIVE_STATUSES)
    if practitioner:
        qs = qs.filter(practitioner=practitioner)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return [(_minutes(a.appointment_time), _minutes(a.appointment_time) + a.duration_minutes) for a in qs]


def _fits(start, duration, shift, booked):
    """True if [start, start+duration) is inside the shift, clear of bookings (with buffer), under the limit."""
    s0, s1 = _minutes(shift.start), _minutes(shift.end)
    end = start + duration
    if start < s0 or end > s1:
        return False
    in_shift = [b for b in booked if b[0] < s1 and b[1] > s0]
    if shift.max_appointments is not None and len(in_shift) >= shift.max_appointments:
        return False
    return all(end + shift.buffer <= b0 or start >= b1 + shift.buffer for b0, b1 in in_shift)


def _now_minutes(day):
    now = timezone.localtime()
    if day < now.date():
        return None  # whole day is past
    return _minutes(now.time()) if day == now.date() else -1


def available_slots(day, practitioner=None, appointment_type='physical', duration=None):
    """Bookable start times ('HH:MM') for the day."""
    now_min = _now_minutes(day)
    if now_min is None:
        return []
    booked = _booked(practitioner, day)
    slots = set()
    for shift in shifts_for(practitioner, day, appointment_type):
        length = duration or shift.length
        for start in range(_minutes(shift.start), _minutes(shift.end), shift.step):
            if start > now_min and _fits(start, length, shift, booked):
                slots.add(start)
    return [f'{m // 60:02d}:{m % 60:02d}' for m in sorted(slots)]


def check_bookable(practitioner, day, start_time, duration, appointment_type='physical', exclude_id=None):
    """None if the booking is allowed, otherwise a message for the user."""
    if practitioner is not None and not practitioner.is_active:
        return 'This practitioner is not taking appointments.'
    if duration <= 0 or duration > 8 * 60:
        return 'Invalid appointment duration.'
    now_min = _now_minutes(day)
    start = _minutes(start_time)
    if now_min is None or start <= now_min:
        return 'This time is in the past.'
    shifts = shifts_for(practitioner, day, appointment_type)
    if not shifts:
        return 'The clinic or practitioner is not available on this day.'
    booked = _booked(practitioner, day, exclude_id)
    if any(_fits(start, duration, s, booked) for s in shifts):
        return None
    if not any(_minutes(s.start) <= start and start + duration <= _minutes(s.end) for s in shifts):
        return 'This time is outside working hours.'
    return 'This time slot is no longer available. Please choose another slot.'


@contextmanager
def booking_lock(practitioner_id, day):
    """Serialize bookings for one practitioner-day so two requests cannot both pass the check.
    Use as the OUTER block around transaction.atomic(), so the row is committed before release."""
    if connection.vendor != 'mysql':
        yield  # shortcut: no lock on other databases; MySQL/MariaDB is the supported engine
        return
    name = f'appt:{practitioner_id or "clinic"}:{day}'
    with connection.cursor() as c:
        c.execute('SELECT GET_LOCK(%s, 10)', [name])
        if c.fetchone()[0] != 1:
            raise BookingError('The schedule is busy. Please try again.')
    try:
        yield
    finally:
        with connection.cursor() as c:
            c.execute('SELECT RELEASE_LOCK(%s)', [name])


def parse_day_time(date_str, time_str):
    """Parse 'YYYY-MM-DD' and 'HH:MM[:SS]'; raises BookingError on bad input."""
    try:
        day = datetime.strptime(date_str, '%Y-%m-%d').date()
        t = datetime.strptime(time_str[:5], '%H:%M').time()
    except (TypeError, ValueError):
        raise BookingError('Invalid date or time.')
    return day, t
