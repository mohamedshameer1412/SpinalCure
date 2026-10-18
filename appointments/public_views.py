"""Self-service pages for patients/guests, reached by the secret link in their confirmation email."""
from datetime import datetime

from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from . import scheduling as sch
from .models import Appointment, BookingSettings


def _get(token):
    if not token or len(token) > 64:
        raise Http404
    return get_object_or_404(Appointment.objects.select_related('practitioner'), manage_token=token)


@ratelimit(key='ip', rate='60/h', method=['GET', 'POST'], block=True)
def manage(request, token):
    """Show the booking; cancel or reschedule while the clinic's cutoff allows."""
    appt = _get(token)
    cfg = BookingSettings.get()
    can_change = appt.status in ('scheduled', 'confirmed')
    too_late = can_change and appt.starts_at - sch._now() < sch.timedelta(hours=cfg.cancel_cutoff_hours)
    if request.method == 'POST' and can_change:
        action = request.POST.get('action')
        try:
            if action == 'cancel':
                sch.cancel(appt, reason=request.POST.get('reason', ''), by_patient=True)
                messages.success(request, _('Your appointment has been cancelled.'))
            elif action == 'reschedule':
                day = datetime.strptime(request.POST.get('date', ''), '%Y-%m-%d').date()
                t = datetime.strptime(request.POST.get('time', ''), '%H:%M').time()
                new = sch.reschedule(appt, day=day, start_time=t, by_patient=True)
                messages.success(request, _('Your appointment has been moved.'))
                return redirect('appointment_manage', token=new.manage_token)
            else:
                messages.error(request, _('Unknown action.'))
        except ValueError:
            messages.error(request, _('Please choose a valid date and time.'))
        except sch.SchedulingError as exc:
            messages.error(request, _(exc.message))
        return redirect('appointment_manage', token=appt.manage_token)
    # Only what the holder of the link needs: no diagnosis, notes or other people's data.
    return render(request, 'appointments/manage.html', {
        'appt': appt, 'can_change': can_change and not too_late, 'too_late': too_late,
        'cutoff_hours': cfg.cancel_cutoff_hours,
    })


@require_GET
@ratelimit(key='ip', rate='120/h', method='GET', block=True)
def manage_slots(request, token):
    appt = _get(token)
    try:
        day = datetime.strptime(request.GET.get('date', ''), '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': gettext('Invalid date.')}, status=400)
    from django.utils.formats import time_format
    slots = sch.generate_slots(appt.practitioner, day, appt.appointment_type, appt.duration_minutes, exclude=appt) \
        if appt.practitioner_id else []
    return JsonResponse({'slots': [{'value': s.label, 'label': time_format(s.time, 'TIME_FORMAT')} for s in slots]})
