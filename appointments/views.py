from django.utils.translation import gettext
from django.contrib.auth.decorators import login_required
from django_ratelimit.decorators import ratelimit
from spinalcure.rbac import has_capability, require_capability
from patients.search import patient_q
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse
from datetime import datetime, date, timedelta, time

from spinalcure.utils import SpinalCureExport, decode_b64uuid, log_action, parse_uuid_param
from clinic.models import Practitioner, ClinicProfile
from patients.models import Patient
from appointments.models import Appointment, DoctorAvailability

@require_capability('appointments.manage')
def appointment_calendar_view(request):
    
    # Export URLs (no filters on main calendar typically, or use defaults)
    params = "" 
    
    import json
    patients = Patient.objects.all().order_by('name')
    practitioners = Practitioner.objects.all().order_by('name')
    
    patients_json = json.dumps([
        {'value': str(p.id), 'label': f"{p.name} ({p.phone})"} for p in patients
    ])
    
    practitioners_json = json.dumps([
        {'value': str(dr.id), 'label': dr.name} for dr in practitioners
    ])

    context = {
        'patients': patients,
        'practitioners': practitioners,
        'patients_json': patients_json,
        'practitioners_json': practitioners_json,
        'status_choices': Appointment.STATUS_CHOICES,
        'clinic': ClinicProfile.objects.first(),
        'export_appointments_excel_url': reverse('export_appointments_excel') + params,
        'export_appointments_csv_url': reverse('export_appointments_csv') + params,
        'export_appointments_pdf_url': reverse('export_appointments_pdf') + params,
        'export_appointments_copy_url': reverse('export_appointments_copy') + params,
        'export_appointments_print_url': reverse('export_appointments_print') + params,
    }
    return render(request, 'appointments/calendar.html', context)

@login_required
def appointment_list_view(request):
    """List all appointments with search and filters."""
    if not has_capability(request.user, 'appointments.manage'):
        messages.error(request, gettext('You do not have permission to view this page.'))
        return redirect('dashboard')
    
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    practitioner_id = request.GET.get('practitioner', '')
    date_filter = request.GET.get('date', '')
    
    appointments = Appointment.objects.select_related('patient', 'practitioner').order_by('-appointment_date', '-appointment_time')
    
    if query:
        appointments = appointments.filter(
            patient_q(query, 'patient__', ('name', 'phone', 'email')) |
            Q(reason__icontains=query)
        )
    if status_filter:
        appointments = appointments.filter(status=status_filter)
    if practitioner_id:
        appointments = appointments.filter(practitioner_id=practitioner_id)
    if date_filter:
        appointments = appointments.filter(appointment_date=date_filter)
        
    # Pagination
    paginator = Paginator(appointments, 10)  # Show 10 appointments per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
        
    # Export URLs with current filters
    params = f"?q={query}&status={status_filter}&practitioner={practitioner_id}&date={date_filter}"
    
    context = {
        'appointments': page_obj,
        'practitioners': Practitioner.objects.all(),
        'status_choices': Appointment.STATUS_CHOICES,
        'search_query': query,
        'filters': {
            'q': query,
            'status': status_filter,
            'practitioner': practitioner_id,
            'date': date_filter,
        },
        'export_appointments_excel_url': reverse('export_appointments_excel') + params,
        'export_appointments_csv_url': reverse('export_appointments_csv') + params,
        'export_appointments_pdf_url': reverse('export_appointments_pdf') + params,
        'export_appointments_copy_url': reverse('export_appointments_copy') + params,
        'export_appointments_print_url': reverse('export_appointments_print') + params,
        'clinic': ClinicProfile.objects.first(),
    }
    
    if request.headers.get('HX-Request'):
        return render(request, 'appointments/partials/appointment_list_partial.html', context)

    return render(request, 'appointments/appointment_list.html', context)

def _get_filtered_appointments(request):
    query = request.GET.get('q', '')
    date_filter = request.GET.get('date', '')
    practitioner_id = request.GET.get('practitioner', '')
    
    appointments = Appointment.objects.all().select_related('patient', 'practitioner').order_by('-appointment_date', '-appointment_time')
    
    if query:
        appointments = appointments.filter(
            patient_q(query, 'patient__', ('name', 'phone', 'email'))
        )
    if date_filter:
        appointments = appointments.filter(appointment_date=date_filter)
    if practitioner_id:
        appointments = appointments.filter(practitioner_id=practitioner_id)
    return appointments, query

def _appointment_mapping(a):
    return [
        a.patient.name,
        a.practitioner.name if a.practitioner else "Not Assigned",
        a.appointment_date.strftime('%Y-%m-%d'),
        a.appointment_time.strftime('%H:%M'),
        a.get_status_display(),
        a.reason
    ]

@require_capability('appointments.manage')
def export_appointments_excel(request):
    appointments, _ = _get_filtered_appointments(request)
    headers = ["Patient", "Practitioner", "Phone Number", "Date", "Time","Reason","Status"]
    def copy_mapping(a):
        return [
            a.patient.name,
            a.practitioner.name if a.practitioner else "N/A",
            a.patient.phone,
            a.appointment_date.strftime('%Y-%m-%d'),
            a.appointment_time.strftime('%H:%M'),
            a.reason,
            a.get_status_display()
        ]
    return SpinalCureExport.to_excel(appointments, headers, copy_mapping, "Appointments", "appointments")

@require_capability('appointments.manage')
def export_appointments_csv(request):
    appointments, _ = _get_filtered_appointments(request)
    headers = ["Patient", "Practitioner", "Phone Number", "Date", "Time","Reason","Status"]
    def copy_mapping(a):
        return [
            a.patient.name,
            a.practitioner.name if a.practitioner else "N/A",
            a.patient.phone,
            a.appointment_date.strftime('%Y-%m-%d'),
            a.appointment_time.strftime('%I:%M %p'),
            a.reason,
            a.get_status_display()
        ]
    return SpinalCureExport.to_csv(appointments, headers, copy_mapping, "appointments")

@require_capability('appointments.manage')
def export_appointments_pdf(request):
    appointments, query = _get_filtered_appointments(request)
    headers = ["Patient", "Practitioner", "Phone Number", "Date", "Time","Reason","Status"]
    def pdf_mapping(a):
        return [
            a.patient.name,
            a.practitioner.name if a.practitioner else "N/A",
            a.patient.phone,
            a.appointment_date.strftime('%Y-%m-%d'),
            a.appointment_time.strftime('%I:%M %p'),
            a.reason,
            a.get_status_display()
        ]
    title = f"Appointments Report {'(Filtered)' if query else ''}"
    return SpinalCureExport.to_pdf(appointments, headers, pdf_mapping, title, "appointments")

@require_capability('appointments.manage')
def export_appointments_copy(request):
    appointments, _ = _get_filtered_appointments(request)
    headers = ["Patient", "Practitioner", "Phone Number", "Date", "Time","Reason","Status"]
    def copy_mapping(a):
        return [
            a.patient.name,
            a.practitioner.name if a.practitioner else "N/A",
            a.patient.phone,
            a.appointment_date.strftime('%Y-%m-%d'),
            a.appointment_time.strftime('%I:%M %p'),
            a.reason,
            a.get_status_display()
        ]
    text = SpinalCureExport.to_text(appointments, headers, copy_mapping)
    return HttpResponse(text, content_type='text/plain')

@require_capability('appointments.manage')
def export_appointments_print(request):
    appointments, query = _get_filtered_appointments(request)
    headers = ["S.No", "Patient", "Practitioner", "Phone Number", "Date", "Time","Reason","Status"]
    rows = [[
        idx,
        a.patient.name,
        a.practitioner.name if a.practitioner else "N/A",
        a.patient.phone,
        a.appointment_date.strftime('%Y-%m-%d'),
        a.appointment_time.strftime('%I:%M %p'),
        a.reason,
        a.get_status_display()
    ] for idx, a in enumerate(appointments, start=1)]
    context = {
        'clinic': ClinicProfile.objects.first(),
        'rows': rows,
        'title': 'Appointments Report',
        'query': query,
        'headers': headers,
        'now': datetime.now(),
    }
    return render(request, 'exports/print_template.html', context)


from spinalcure.decorators import require_pin_auth

@require_capability('appointments.manage')
@require_pin_auth('appointments')
def appointment_delete_view(request, pk):
    """Delete an appointment - requires POST and role check."""
    appointment = get_object_or_404(Appointment, pk=pk)
    
    if request.method == 'POST':
        patient_name = appointment.patient.name
        date = appointment.appointment_date
        appointment_id = appointment.id
        appointment.delete()
        log_action(request, 'delete', 'Appointment', f'Appointment for {patient_name} on {date}', object_id=appointment_id)
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
            return JsonResponse({'status': 'ok', 'message': gettext('Appointment for %(patient_name)s deleted.') % {'patient_name': patient_name}})
            
        messages.success(request, gettext('Appointment for %(patient_name)s on %(date)s deleted.') % {'patient_name': patient_name, 'date': date})
        return redirect('appointment_calendar')
    
    return redirect('appointment_calendar')


@require_capability('appointments.manage')
def appointment_check_collision(request):
    """Check if a doctor already has an appointment at a specific time."""
    practitioner_id = request.GET.get('practitioner')
    app_date = request.GET.get('date')
    app_time = request.GET.get('time')
    exclude_id = request.GET.get('exclude')

    if not all([practitioner_id, app_date, app_time]):
        return JsonResponse({'conflict': False})

    # Basic collision: check if practitioner has ANY appointment at this EXACT time on this date
    # (In a real system, you'd check time ranges/duration overlap)
    qs = Appointment.objects.filter(
        practitioner_id=practitioner_id,
        appointment_date=app_date,
        appointment_time=app_time
    ).exclude(status='cancelled')

    if exclude_id:
        qs = qs.exclude(id=exclude_id)

    conflict = qs.first()
    if conflict:
        return JsonResponse({
            'conflict': True,
            'message': gettext('Dr. %(name)s is already booked for %(name2)s at this time.') % {'name': conflict.practitioner.name, 'name2': conflict.patient.name}
        })

    return JsonResponse({'conflict': False})

@ratelimit(key='ip', rate='120/m', method='GET', block=True)
def get_available_slots(request):
    """
    Bookable start times for one date, driven by practitioner shifts, leave and existing bookings.
    ?date=YYYY-MM-DD [&practitioner=<id>] [&type=physical|online] [&duration=<mins>] [&exclude=<appointment id>]
    Without `practitioner` the union across active practitioners is returned ("any available doctor").
    Only times are exposed; nothing about who holds the other slots.
    """
    from spinalcure.utils import clock
    from . import scheduling as sch

    try:
        day = datetime.strptime(request.GET.get('date', ''), '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': gettext('Invalid or missing date. Use YYYY-MM-DD.')}, status=400)
    appt_type = request.GET.get('type', 'physical')
    if appt_type not in ('physical', 'online'):
        return JsonResponse({'error': gettext('Invalid appointment type.')}, status=400)
    try:
        duration = int(request.GET['duration']) if request.GET.get('duration') else None
    except ValueError:
        return JsonResponse({'error': gettext('Invalid duration.')}, status=400)
    if duration is not None and not (5 <= duration <= 480):
        return JsonResponse({'error': gettext('Duration must be between 5 and 480 minutes.')}, status=400)

    exclude = None
    if request.GET.get('exclude') and request.user.is_authenticated:
        exclude = Appointment.objects.filter(pk=request.GET['exclude']).first()

    qs = Practitioner.objects.filter(is_active=True)
    if request.GET.get('practitioner'):
        practitioner_id = parse_uuid_param(request.GET['practitioner'])
        if practitioner_id is None:
            return JsonResponse({'error': gettext('Unknown practitioner.')}, status=404)
        qs = qs.filter(pk=practitioner_id)
    practitioners = list(qs)
    if request.GET.get('practitioner') and not practitioners:
        return JsonResponse({'error': gettext('Unknown practitioner.')}, status=404)

    seen, slots = set(), []
    for pr in practitioners:
        for slot in sch.generate_slots(pr, day, appt_type, duration, exclude):
            if slot.label not in seen:
                seen.add(slot.label)
                slots.append(slot)
    slots.sort(key=lambda sl: sl.start)

    message = ''
    if not slots:
        message = 'No times are available on this date.'
        if practitioners:
            reasons = {sch._diagnose(pr, day, sch._aware(day, time(12, 0)), sch._aware(day, time(12, 30)),
                                     appt_type, None, sch._now(), sch.BookingSettings.get(), True).code
                       for pr in practitioners}
            if reasons <= {'closed'}:
                message = 'The clinic does not take bookings on this day.'
            elif reasons <= {'blocked'}:
                message = 'The clinic is closed on this date.'
    from django.conf import settings as dj_settings
    return JsonResponse({
        'available_slots': [sl.label for sl in slots],
        'slots': [{'value': sl.label, 'label': clock(sl.time)} for sl in slots],
        'message': message,
        'timezone': dj_settings.TIME_ZONE,
    })
