"""Practitioner availability, leave/holidays and booking rules."""
from datetime import datetime, time

from django.db import transaction
from django.utils.translation import gettext
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from clinic.models import Practitioner
from spinalcure.rbac import MANAGEMENT, has_capability, require_capability
from spinalcure.utils import encode_b64uuid, log_action, parse_uuid_param

from .forms import BookingSettingsForm, ShiftForm, TimeOffForm
from .models import Appointment, BookingSettings, DoctorAvailability, TimeOff


def _is_management(user):
    return user.is_superuser or user.role in MANAGEMENT


def _editable(user, practitioner):
    """Management may edit anyone; a doctor only their own record (matched by email)."""
    if _is_management(user):
        return True
    return bool(practitioner and practitioner.email and practitioner.email.lower() == (user.email or '').lower())


def _practitioner_or_404(pk):
    pk = parse_uuid_param(pk)
    if pk is None:
        raise Http404
    return get_object_or_404(Practitioner, pk=pk)


def _back(practitioner):
    return redirect(reverse('doctor_availability') + f'?practitioner_id={encode_b64uuid(practitioner.pk)}')


def _affected(practitioner, start, end):
    return Appointment.objects.filter(
        practitioner=practitioner, appointment_date__gte=start, appointment_date__lte=end,
        status__in=('scheduled', 'confirmed')).count()


# -- weekly hours: per day an Open switch plus a Morning and an Evening session -----------------------------
SLOT_CHOICES = (15, 20, 30, 45, 60)
SPLIT = time(14, 0)                              # a shift starting before 14:00 is the morning session


def _label(t):
    return datetime(2000, 1, 1, t.hour, t.minute).strftime('%I:%M %p').lstrip('0')


# every quarter hour from 06:00 to 23:00, so people pick a time instead of typing one
TIME_OPTIONS = [(f'{h:02d}:{m:02d}', _label(time(h, m))) for h in range(6, 24) for m in (0, 15, 30, 45) if (h, m) <= (23, 0)]
# morning times run up to 2 PM, evening times start at 2 PM: short lists, and the two sessions can never overlap
MORNING_OPTIONS = [(v, l) for v, l in TIME_OPTIONS if v <= '14:00']
EVENING_OPTIONS = [(v, l) for v, l in TIME_OPTIONS if v >= '14:00']
VALID_MORNING = {v for v, _l in MORNING_OPTIONS}
VALID_EVENING = {v for v, _l in EVENING_OPTIONS}


def _hm(t):
    return t.strftime('%H:%M') if t else ''


def _weekly_rows(shifts):
    """One row per weekday from the stored shifts: the first shift before 14:00 is the morning, the next the evening."""
    rows = []
    for num, label in DoctorAvailability.DAY_CHOICES:
        day = sorted((s for s in shifts if s.day_of_week == num and s.is_available), key=lambda s: s.start_time)
        morning = next((s for s in day if s.start_time < SPLIT), None)
        evening = next((s for s in day if s is not morning), None)
        rows.append({'num': num, 'p': f'd{num}_', 'label': label, 'open': bool(day), 'errors': [],
                     'm_start': _hm(morning and morning.start_time), 'm_end': _hm(morning and morning.end_time),
                     'e_start': _hm(evening and evening.start_time), 'e_end': _hm(evening and evening.end_time)})
    return rows


def _minutes(hm):
    h, m = hm.split(':')
    return int(h) * 60 + int(m)


def _read_weekly(post, slot):
    """Rows from the submitted form, each with its own list of validation errors."""
    rows = []
    for num, label in DoctorAvailability.DAY_CHOICES:
        def g(k, num=num):
            return (post.get(f'd{num}_{k}') or '').strip()
        row = {'num': num, 'p': f'd{num}_', 'label': label, 'open': post.get(f'd{num}_open') == 'on', 'errors': [],
               'm_start': g('m_start'), 'm_end': g('m_end'), 'e_start': g('e_start'), 'e_end': g('e_end')}
        if row['open']:
            for name, a, b, valid in ((gettext('Morning'), 'm_start', 'm_end', VALID_MORNING),
                                      (gettext('Evening'), 'e_start', 'e_end', VALID_EVENING)):
                start, end = row[a], row[b]
                if not start and not end:
                    continue
                if not (start and end):
                    row['errors'].append(gettext('%(s)s: choose both a start and an end time.') % {'s': name})
                elif start not in valid or end not in valid:
                    row['errors'].append(gettext('%(s)s: choose the times from the list.') % {'s': name})
                elif _minutes(end) <= _minutes(start):
                    row['errors'].append(gettext('%(s)s: the end time must be after the start time.') % {'s': name})
                elif _minutes(end) - _minutes(start) < slot:
                    row['errors'].append(gettext('%(s)s: shorter than one %(n)s-minute appointment.') % {'s': name, 'n': slot})
            if not (row['m_start'] or row['m_end'] or row['e_start'] or row['e_end']):
                row['errors'].append(gettext('Choose a morning or an evening session, or switch the day off.'))
        rows.append(row)
    return rows


def _context(request, selected, practitioners, weekly=None, slot=None):
    ctx = {'practitioners': practitioners, 'selected_doc': selected, 'is_management': _is_management(request.user),
           'timeoff_form': TimeOffForm(), 'morning_options': MORNING_OPTIONS, 'evening_options': EVENING_OPTIONS,
           'slot_choices': SLOT_CHOICES}
    if selected:
        shifts = list(DoctorAvailability.objects.filter(practitioner=selected))
        ctx['weekly'] = weekly or _weekly_rows(shifts)
        ctx['slot_minutes'] = slot or (shifts[0].slot_duration_minutes if shifts else 30)
        ctx['time_off'] = TimeOff.objects.filter(practitioner=selected).order_by('-start_date')[:50]
        ctx['clinic_closures'] = TimeOff.objects.filter(practitioner__isnull=True).order_by('-start_date')[:50]
    if _is_management(request.user):
        ctx['settings_form'] = BookingSettingsForm(instance=BookingSettings.get())
    return ctx


def _visible_practitioners(user):
    practitioners = Practitioner.objects.filter(is_active=True).order_by('name')
    return practitioners if _is_management(user) else [p for p in practitioners if _editable(user, p)]


@require_capability('schedule.manage')
def availability(request):
    practitioners = _visible_practitioners(request.user)
    selected = None
    raw = parse_uuid_param(request.GET.get('practitioner_id'))
    if raw:
        selected = next((p for p in practitioners if p.pk == raw), None)
    selected = selected or (practitioners[0] if practitioners else None)
    return render(request, 'appointments/availability.html', _context(request, selected, practitioners))


@require_POST
@require_capability('schedule.manage')
def weekly_save(request, practitioner_id):
    """Save the whole week at once. Validated per day; on any error nothing is saved and the form is shown again
    with the errors beside the days they belong to."""
    pr = _practitioner_or_404(practitioner_id)
    if not _editable(request.user, pr):
        messages.error(request, gettext('You can only edit your own schedule.'))
        return _back(pr)
    try:
        slot = int(request.POST.get('slot_minutes', 30))
    except ValueError:
        slot = 0
    rows = _read_weekly(request.POST, slot)
    bad_slot = slot not in SLOT_CHOICES
    if bad_slot or any(r['errors'] for r in rows):
        messages.error(request, gettext('Choose the appointment length from the list.') if bad_slot
                       else gettext('Nothing was saved. Fix the days marked in red and save again.'))
        return render(request, 'appointments/availability.html',
                      _context(request, pr, _visible_practitioners(request.user), weekly=rows,
                               slot=30 if bad_slot else slot), status=400)
    with transaction.atomic():
        DoctorAvailability.objects.filter(practitioner=pr).delete()
        for r in rows:
            if not r['open']:
                continue
            for a, b in (('m_start', 'm_end'), ('e_start', 'e_end')):
                if r[a]:
                    shift = DoctorAvailability(practitioner=pr, day_of_week=r['num'], slot_duration_minutes=slot,
                                               start_time=datetime.strptime(r[a], '%H:%M').time(),
                                               end_time=datetime.strptime(r[b], '%H:%M').time())
                    shift.full_clean()
                    shift.save()
    log_action(request, 'update', 'Availability', f'{pr.name}: weekly hours', object_id=pr.pk)
    messages.success(request, gettext('Weekly hours saved.'))
    return _back(pr)


@require_POST
@require_capability('schedule.manage')
def shift_save(request, practitioner_id):
    pr = _practitioner_or_404(practitioner_id)
    if not _editable(request.user, pr):
        messages.error(request, gettext('You can only edit your own schedule.'))
        return _back(pr)
    instance = None
    if request.POST.get('shift_id'):
        instance = get_object_or_404(DoctorAvailability, pk=request.POST['shift_id'], practitioner=pr)
    form = ShiftForm(request.POST, instance=instance or DoctorAvailability(practitioner=pr))
    if form.is_valid():
        shift = form.save()
        log_action(request, 'update' if instance else 'create', 'Availability',
                   f'{pr.name} {shift.get_day_of_week_display()} {shift.start_time:%H:%M}-{shift.end_time:%H:%M}',
                   object_id=shift.pk)
        messages.success(request, gettext('Shift saved.'))
    else:
        messages.error(request, 'Shift not saved: ' + '; '.join(
            f'{(form.fields[f].label if f in form.fields else "") or f}: {" ".join(e)}' for f, e in form.errors.items()
        ).replace('__all__: ', ''))
    return _back(pr)


@require_POST
@require_capability('schedule.manage')
def shift_delete(request, practitioner_id, pk):
    pr = _practitioner_or_404(practitioner_id)
    if not _editable(request.user, pr):
        messages.error(request, gettext('You can only edit your own schedule.'))
        return _back(pr)
    shift = get_object_or_404(DoctorAvailability, pk=pk, practitioner=pr)
    shift.delete()
    log_action(request, 'delete', 'Availability', f'{pr.name} {shift.get_day_of_week_display()}', object_id=pk)
    messages.success(request, gettext('Shift removed. Existing appointments are unchanged.'))
    return _back(pr)


@require_POST
@require_capability('schedule.manage')
def timeoff_save(request, practitioner_id):
    """practitioner_id 'clinic' closes the whole clinic (management only)."""
    if practitioner_id == 'clinic':
        if not _is_management(request.user):
            messages.error(request, gettext('Only management can close the whole clinic.'))
            return redirect('doctor_availability')
        pr, target = None, None
    else:
        pr = target = _practitioner_or_404(practitioner_id)
        if not _editable(request.user, pr):
            messages.error(request, gettext('You can only edit your own schedule.'))
            return _back(pr)
    data = request.POST.copy()
    if data.get('start_date') and not data.get('end_date'):
        data['end_date'] = data['start_date']                  # one day: only "from" is needed
    data.setdefault('kind', 'leave' if target else 'holiday')
    form = TimeOffForm(data, instance=TimeOff(practitioner=target, created_by=request.user))
    if form.is_valid():
        off = form.save()
        log_action(request, 'create', 'TimeOff', str(off), object_id=off.pk)
        clash = 0
        for p in ([target] if target else Practitioner.objects.filter(is_active=True)):
            clash += _affected(p, off.start_date, off.end_date)
        messages.success(request, gettext('Time off saved.'))
        if clash:
            messages.warning(request, gettext('%(clash)s existing appointment(s) fall in this period. They were not changed. Reschedule or cancel them from the calendar.') % {'clash': clash})
    else:
        messages.error(request, 'Time off not saved: ' + '; '.join(
            f'{f}: {" ".join(e)}' for f, e in form.errors.items()).replace('__all__: ', ''))
    return _back(pr) if pr else redirect('doctor_availability')


@require_POST
@require_capability('schedule.manage')
def timeoff_delete(request, pk):
    off = get_object_or_404(TimeOff, pk=pk)
    if off.practitioner_id is None and not _is_management(request.user):
        messages.error(request, gettext('Only management can remove a clinic closure.'))
        return redirect('doctor_availability')
    if off.practitioner_id and not _editable(request.user, off.practitioner):
        messages.error(request, gettext('You can only edit your own schedule.'))
        return redirect('doctor_availability')
    pr = off.practitioner
    off.delete()
    log_action(request, 'delete', 'TimeOff', str(off), object_id=pk)
    messages.success(request, gettext('Time off removed.'))
    return _back(pr) if pr else redirect('doctor_availability')


@require_POST
@require_capability('schedule.manage')
def booking_settings_save(request):
    if not _is_management(request.user):
        messages.error(request, gettext('Only management can change booking rules.'))
        return redirect('doctor_availability')
    form = BookingSettingsForm(request.POST, instance=BookingSettings.get())
    if form.is_valid():
        form.save()
        log_action(request, 'update', 'BookingSettings', 'Booking rules')
        messages.success(request, gettext('Booking rules saved.'))
    else:
        messages.error(request, 'Booking rules not saved: ' + '; '.join(
            f'{f}: {" ".join(e)}' for f, e in form.errors.items()))
    return redirect('doctor_availability')
