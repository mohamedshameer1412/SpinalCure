from django.contrib.auth.decorators import login_required
from spinalcure.decorators import role_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse
from datetime import datetime, date, timedelta, time

from spinalcure.utils import SpinalCureExport, decode_b64uuid, encode_b64uuid, log_action
from clinic.models import Practitioner, ClinicProfile
from patients.models import Patient
from appointments.models import Appointment, DoctorAvailability, PractitionerLeave
from django import forms

@role_required('appointments_view')
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

_INPUT_CLASS = 'w-full px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500'


def _style(form):
    for f in form.fields.values():
        if not isinstance(f.widget, forms.CheckboxInput):
            f.widget.attrs.setdefault('class', _INPUT_CLASS)


class _ShiftForm(forms.ModelForm):
    class Meta:
        model = DoctorAvailability
        fields = ['day_of_week', 'start_time', 'end_time', 'slot_duration_minutes', 'buffer_minutes', 'max_appointments']
        widgets = {'start_time': forms.TimeInput(attrs={'type': 'time'}), 'end_time': forms.TimeInput(attrs={'type': 'time'})}

    def __init__(self, *args, practitioner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.practitioner = practitioner
        _style(self)

    def clean_slot_duration_minutes(self):
        v = self.cleaned_data['slot_duration_minutes']
        if not 5 <= v <= 240:
            raise forms.ValidationError('Slot length must be between 5 and 240 minutes.')
        return v


class _LeaveForm(forms.ModelForm):
    clinic_wide = forms.BooleanField(required=False, label='Clinic holiday (all practitioners)')

    class Meta:
        model = PractitionerLeave
        fields = ['start_date', 'end_date', 'reason']
        widgets = {'start_date': forms.DateInput(attrs={'type': 'date'}), 'end_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)


def _editable_practitioners(user):
    """Admins manage everyone; a doctor only their own practitioner profile (matched by email)."""
    qs = Practitioner.objects.order_by('name')
    if user.can('site_manage'):
        return qs
    return qs.filter(email__iexact=user.email) if user.email else qs.none()


@role_required('availability_manage')
def doctor_availability_view(request):
    practitioners = _editable_practitioners(request.user)
    pid = request.POST.get('practitioner_id') or request.GET.get('practitioner_id')
    selected_doc = (practitioners.filter(pk=decode_b64uuid(pid)).first() if pid else None) or practitioners.first()
    shift_form, leave_form = _ShiftForm(practitioner=selected_doc), _LeaveForm()

    if request.method == 'POST' and selected_doc:
        action = request.POST.get('action')
        if action == 'add_shift':
            shift_form = _ShiftForm(request.POST, practitioner=selected_doc)
            if shift_form.is_valid():
                shift = shift_form.save()
                log_action(request, 'create', 'DoctorAvailability', str(shift), object_id=shift.pk)
                messages.success(request, 'Shift added.')
                return redirect(f"{reverse('doctor_availability')}?practitioner_id={encode_b64uuid(selected_doc.pk)}")
        elif action == 'delete_shift':
            shift = DoctorAvailability.objects.filter(pk=request.POST.get('id'), practitioner=selected_doc).first()
            if shift:
                log_action(request, 'delete', 'DoctorAvailability', str(shift), object_id=shift.pk)
                shift.delete()
                messages.success(request, 'Shift removed. Existing appointments are unchanged.')
            return redirect(f"{reverse('doctor_availability')}?practitioner_id={encode_b64uuid(selected_doc.pk)}")
        elif action == 'add_leave':
            leave_form = _LeaveForm(request.POST)
            if leave_form.is_valid():
                if leave_form.cleaned_data['clinic_wide'] and not request.user.can('site_manage'):
                    messages.error(request, 'Only clinic administrators can add clinic holidays.')
                else:
                    leave = leave_form.save(commit=False)
                    leave.practitioner = None if leave_form.cleaned_data['clinic_wide'] else selected_doc
                    leave.save()
                    log_action(request, 'create', 'PractitionerLeave', str(leave), object_id=leave.pk)
                    clashes = Appointment.objects.filter(
                        appointment_date__range=(leave.start_date, leave.end_date),
                        status__in=('scheduled', 'confirmed'),
                        **({} if leave.practitioner is None else {'practitioner': selected_doc}))
                    n = clashes.count()
                    messages.success(request, 'Leave saved.' + (f' {n} existing appointment(s) fall in this period and need rescheduling.' if n else ''))
                    return redirect(f"{reverse('doctor_availability')}?practitioner_id={encode_b64uuid(selected_doc.pk)}")
        elif action == 'delete_leave':
            leave = PractitionerLeave.objects.filter(pk=request.POST.get('id')).first()
            allowed = leave and (leave.practitioner_id == selected_doc.pk or (leave.practitioner_id is None and request.user.can('site_manage')))
            if allowed:
                log_action(request, 'delete', 'PractitionerLeave', str(leave), object_id=leave.pk)
                leave.delete()
                messages.success(request, 'Leave removed.')
            return redirect(f"{reverse('doctor_availability')}?practitioner_id={encode_b64uuid(selected_doc.pk)}")

    availabilities = DoctorAvailability.objects.filter(practitioner=selected_doc).order_by('day_of_week', 'start_time') if selected_doc else []
    leaves = PractitionerLeave.objects.filter(
        Q(practitioner=selected_doc) | Q(practitioner__isnull=True), end_date__gte=date.today()
    ).select_related('practitioner') if selected_doc else []
    return render(request, 'appointments/availability.html', {
        'practitioners': practitioners, 'selected_doc': selected_doc, 'availabilities': availabilities,
        'leaves': leaves, 'shift_form': shift_form, 'leave_form': leave_form,
    })


@role_required('appointments_view')
def appointment_list_view(request):
    """List all appointments with search and filters."""
    
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    practitioner_id = request.GET.get('practitioner', '')
    date_filter = request.GET.get('date', '')
    
    appointments = Appointment.objects.select_related('patient', 'practitioner').order_by('-appointment_date', '-appointment_time')
    
    if query:
        appointments = appointments.filter(
            Q(patient__in=Patient.search(Patient.objects.all(), query)) |
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
            Q(patient__in=Patient.search(Patient.objects.all(), query))
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

@role_required('appointments_view')
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

@role_required('appointments_view')
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

@role_required('appointments_view')
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

@role_required('appointments_view')
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

@role_required('appointments_view')
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

@role_required('appointments_delete')
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


def _practitioner_from_param(value):
    """Accept a plain UUID (staff calendar) or base64 id (public site)."""
    import uuid as uuid_mod
    try:
        pk = uuid_mod.UUID(str(value))
    except ValueError:
        pk = decode_b64uuid(str(value))
    return Practitioner.objects.filter(pk=pk, is_active=True).first() if pk else None


def get_available_slots(request):
    """Public: bookable start times for a date, optional practitioner and type (physical/online)."""
    from .scheduling import available_slots
    practitioner = None
    pid = request.GET.get('practitioner')
    if pid:
        practitioner = _practitioner_from_param(pid)
        if practitioner is None:
            return JsonResponse({'error': 'Unknown practitioner'}, status=400)
    try:
        day = datetime.strptime(request.GET.get('date', ''), '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
    appointment_type = 'online' if request.GET.get('type') == 'online' else 'physical'
    return JsonResponse({'available_slots': available_slots(day, practitioner, appointment_type)})
