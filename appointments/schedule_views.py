"""Practitioner availability, leave/holidays and booking rules."""
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


@require_capability('schedule.manage')
def availability(request):
    practitioners = Practitioner.objects.filter(is_active=True).order_by('name')
    if not _is_management(request.user):
        practitioners = [p for p in practitioners if _editable(request.user, p)]
    selected = None
    raw = parse_uuid_param(request.GET.get('practitioner_id'))
    if raw:
        selected = next((p for p in practitioners if p.pk == raw), None)
    selected = selected or (practitioners[0] if practitioners else None)

    ctx = {'practitioners': practitioners, 'selected_doc': selected, 'is_management': _is_management(request.user),
           'days': DoctorAvailability.DAY_CHOICES, 'shift_form': ShiftForm(), 'timeoff_form': TimeOffForm()}
    if selected:
        shifts = DoctorAvailability.objects.filter(practitioner=selected)
        ctx['shifts_json'] = {str(sh.pk): {
            'day_of_week': sh.day_of_week, 'start_time': sh.start_time.strftime('%H:%M'),
            'end_time': sh.end_time.strftime('%H:%M'), 'slot_duration_minutes': sh.slot_duration_minutes,
            'buffer_minutes': sh.buffer_minutes, 'appointment_type': sh.appointment_type,
            'break_start': sh.break_start.strftime('%H:%M') if sh.break_start else '',
            'break_end': sh.break_end.strftime('%H:%M') if sh.break_end else '',
            'max_appointments': sh.max_appointments or '', 'is_available': sh.is_available,
            'valid_from': sh.valid_from.isoformat() if sh.valid_from else '',
            'valid_until': sh.valid_until.isoformat() if sh.valid_until else '',
        } for sh in shifts}
        ctx['timeoff_url_template'] = reverse('timeoff_save', args=['__T__'])
        ctx['by_day'] = [(num, label, [s for s in shifts if s.day_of_week == num]) for num, label in DoctorAvailability.DAY_CHOICES]
        ctx['time_off'] = TimeOff.objects.filter(practitioner=selected).order_by('-start_date')[:50]
        ctx['clinic_closures'] = TimeOff.objects.filter(practitioner__isnull=True).order_by('-start_date')[:50]
    if _is_management(request.user):
        ctx['settings_form'] = BookingSettingsForm(instance=BookingSettings.get())
    return render(request, 'appointments/availability.html', ctx)


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
    form = TimeOffForm(request.POST, instance=TimeOff(practitioner=target, created_by=request.user))
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
