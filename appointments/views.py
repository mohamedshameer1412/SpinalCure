from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse
from datetime import datetime, date, timedelta, time

from spinalcure.utils import SpinalCureExport, decode_b64uuid, log_action
from clinic.models import Practitioner, ClinicProfile
from patients.models import Patient
from appointments.models import Appointment, DoctorAvailability

@login_required
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
def doctor_availability_view(request):
    practitioners = Practitioner.objects.all()
    # If a specific doctor is selected or default to the first one for the UI
    selected_doc_id = request.GET.get('practitioner_id')
    if selected_doc_id:
        selected_doc_id = decode_b64uuid(selected_doc_id)
    selected_doc = practitioners.filter(id=selected_doc_id).first() if selected_doc_id else practitioners.first()
    
    availabilities = DoctorAvailability.objects.filter(practitioner=selected_doc).order_by('day_of_week', 'start_time') if selected_doc else []
    
    context = {
        'practitioners': practitioners,
        'selected_doc': selected_doc,
        'availabilities': availabilities,
    }
    return render(request, 'appointments/availability.html', context)

@login_required
def appointment_list_view(request):
    """List all appointments with search and filters."""
    if not (request.user.role in ['superadmin', 'doctor'] or request.user.is_staff):
        messages.error(request, 'You do not have permission to view this page.')
        return redirect('dashboard')
    
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    practitioner_id = request.GET.get('practitioner', '')
    date_filter = request.GET.get('date', '')
    
    appointments = Appointment.objects.select_related('patient', 'practitioner').order_by('-appointment_date', '-appointment_time')
    
    if query:
        appointments = appointments.filter(
            Q(patient__name__icontains=query) | 
            Q(patient__phone__icontains=query) |
            Q(patient__email__icontains=query) |
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
            Q(patient__name__icontains=query) | 
            Q(patient__phone__icontains=query) |
            Q(patient__email__icontains=query)
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

@login_required
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

@login_required
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

@login_required
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

@login_required
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

@login_required
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

@login_required
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
            return JsonResponse({'status': 'ok', 'message': f'Appointment for {patient_name} deleted.'})
            
        messages.success(request, f'Appointment for {patient_name} on {date} deleted.')
        return redirect('appointment_calendar')
    
    return redirect('appointment_calendar')


@login_required
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
            'message': f'Dr. {conflict.practitioner.name} is already booked for {conflict.patient.name} at this time.'
        })

    return JsonResponse({'conflict': False})

def get_available_slots(request):
    """
    Returns available 15-minute time slots for a given date, practitioner, and appointment type.
    """
    date_str = request.GET.get('date')
    practitioner_id = request.GET.get('practitioner')
    if practitioner_id:
        try:
            practitioner_id = decode_b64uuid(practitioner_id)
        except Exception:
            pass
            
    appointment_type = request.GET.get('type', 'physical') # 'physical' or 'online'
    
    if not date_str:
        return JsonResponse({'error': 'Date is required'}, status=400)
        
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
    
    # 1. Generate all possible slots based on the clinic physical/online hours
    day_of_week = target_date.weekday() # 0 = Monday, 6 = Sunday
    possible_slots = []

    # Sunday (6): Closed for both physical and online
    if day_of_week == 6:
        return JsonResponse({'available_slots': []})

    if appointment_type == 'online':
        # Online Hours: Mon-Sat 9 AM - 5 PM
        current_time = datetime.combine(target_date, time(9, 0))
        end_time = datetime.combine(target_date, time(17, 0))
        while current_time < end_time:
            possible_slots.append(current_time.time())
            current_time += timedelta(minutes=15)
    else:
        # Physical Hours
        # Friday (4): Evening only (6:30 PM - 8:30 PM)
        if day_of_week == 4:
            current_time = datetime.combine(target_date, time(18, 30))
            end_time = datetime.combine(target_date, time(20, 30))
            while current_time < end_time:
                possible_slots.append(current_time.time())
                current_time += timedelta(minutes=15)
        # Mon, Tue, Wed, Thu, Sat: Morning (10 AM - 1 PM) and Evening (5:30 PM - 8:30 PM)
        else:
            # Morning shift
            current_time = datetime.combine(target_date, time(10, 0))
            end_time = datetime.combine(target_date, time(13, 0))
            while current_time < end_time:
                possible_slots.append(current_time.time())
                current_time += timedelta(minutes=15)
            
            # Evening shift
            current_time = datetime.combine(target_date, time(17, 30))
            end_time = datetime.combine(target_date, time(20, 30))
            while current_time < end_time:
                possible_slots.append(current_time.time())
                current_time += timedelta(minutes=15)

    # 2. Filter out slots that have already passed if the date is today
    from django.utils import timezone
    now = timezone.now()
    if target_date == now.date():
        possible_slots = [s for s in possible_slots if s > now.time()]
    elif target_date < now.date():
        possible_slots = []

    # 3. Query existing non-cancelled appointments to find booked slots
    booked_appointments = Appointment.objects.filter(
        appointment_date=target_date
    ).exclude(status__in=['cancelled', 'no_show', 'rescheduled'])
    
    if practitioner_id:
        booked_appointments = booked_appointments.filter(practitioner_id=practitioner_id)
        
    booked_times = []
    for appt in booked_appointments:
        appt_start = datetime.combine(target_date, appt.appointment_time)
        appt_end = appt_start + timedelta(minutes=appt.duration_minutes)
        c_time = appt_start
        while c_time < appt_end:
            booked_times.append(c_time.time())
            c_time += timedelta(minutes=15)
            
    # 4. Remove booked slots
    available_slots = [
        s.strftime('%H:%M') for s in possible_slots 
        if s not in booked_times
    ]
    
    return JsonResponse({'available_slots': available_slots})
