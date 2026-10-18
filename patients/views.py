from django.utils.translation import gettext
from django.contrib.auth.decorators import login_required
from spinalcure.rbac import has_capability, require_capability, capability_rw_permission
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Avg, Sum, Q
from django.core.paginator import Paginator
from .models import Patient, Session, PatientReview, TreatmentPlan
from clinic.models import Practitioner, ClinicProfile
from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from .serializers import PatientSerializer, PatientDetailSerializer, SessionSerializer
from spinalcure.permissions import IsDoctor, IsAuthenticated
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import datetime
from django.core.mail import send_mail
from django.conf import settings
import logging
import random
import secrets
from datetime import datetime, date, timedelta
from django.db.models import Q
from spinalcure.utils import SpinalCureExport
import os
from spinalcure.decorators import superadmin_required, require_pin_auth
from spinalcure.utils import SpinalCureExport, log_action
logger = logging.getLogger(__name__)


class PatientViewSet(viewsets.ModelViewSet):
    """
    ViewSet for patient management.
    Doctors and admins can view/create patients.
    """
    queryset = Patient.objects.prefetch_related('sessions', 'payments', 'appointments').order_by('-registered_date')
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    ordering_fields = ['registered_date', 'name']
    permission_classes = [IsAuthenticated, capability_rw_permission('patients.view', 'patients.edit')]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PatientDetailSerializer
        return PatientSerializer

    def get_queryset(self):
        """Optimized queryset for patient with related data."""
        queryset = Patient.objects.prefetch_related('sessions', 'payments', 'appointments')
        if self.action == 'retrieve':
            return queryset
        term = self.request.query_params.get('search', '').strip()
        if term:  # encrypted columns cannot be searched in SQL; see patients/search.py
            from .search import patient_q
            queryset = queryset.filter(patient_q(term))
        return queryset.order_by('-registered_date')


class SessionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for treatment session management.
    """
    queryset = Session.objects.all().order_by('-session_date', '-session_number').select_related(
        'patient', 'consulted_by'
    )
    serializer_class = SessionSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['patient', 'consulted_by', 'session_date']
    ordering_fields = ['session_date', 'patient']
    permission_classes = [IsAuthenticated, capability_rw_permission('clinical.view', 'clinical.edit')]


@login_required
def patient_list_view(request):
    """List all patients - admin panel view with search."""
    if not has_capability(request.user, 'patients.view'):
        messages.error(request, gettext('You do not have permission to view this page.'))
        return redirect('dashboard')
    
    query = request.GET.get('q', '')
    patients = Patient.objects.prefetch_related('sessions', 'payments', 'appointments')
    
    if query:
        from .search import patient_q
        patients = patients.filter(patient_q(query)).order_by('-registered_date')
    else:
        patients = patients.order_by('-registered_date')

    # Pagination
    paginator = Paginator(patients, 10)  # Show 10 patients per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
        
    # Export URLs
    base_export_params = f"?q={query}" if query else ""
    from django.urls import reverse
    
    context = {
        'patients': page_obj,
        'search_query': query,
        'export_patients_excel_url': reverse('export_patients_excel') + base_export_params,
        'export_patients_csv_url': reverse('export_patients_csv') + base_export_params,
        'export_patients_pdf_url': reverse('export_patients_pdf') + base_export_params,
        'export_patients_copy_url': reverse('export_patients_copy') + base_export_params,
        'export_patients_print_url': reverse('export_patients_print') + base_export_params,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'patients/partials/patient_list_partial.html', context)
        
    return render(request, 'patients/patient_list.html', context)

def _get_filtered_patients(request):
    query = request.GET.get('q', '')
    patients = Patient.objects.all().order_by('-registered_date')
    if query:
        from .search import patient_q
        patients = patients.filter(patient_q(query))
    return patients, query

def _get_patient_export_rows(patients):
    """Helper to prepare row data with S.No and Photo path for export."""
    rows = []
    for i, p in enumerate(patients, 1):
        # We use path for embedding in PDF/Excel, and fall back to URL for CSV/Copy if needed
        photo_val = p.photo.path if p.photo and os.path.exists(p.photo.path) else ""
        rows.append([
            i,
            photo_val,
            p.name,
            p.phone,
            p.email,
            p.address,
            p.get_gender_display(),
            p.date_of_birth.strftime('%Y-%m-%d') if p.date_of_birth else "",
            p.chief_complaint,
            f"{p.progress_percentage}%",
            p.registered_date.strftime('%Y-%m-%d')
        ])
    return rows

def _get_patient_export_rows(patients):
    """Helper to prepare row data with S.No and Photo path for export."""
    rows = []
    for i, p in enumerate(patients, 1):
        photo_val = p.photo.path if p.photo and os.path.exists(p.photo.path) else ""
        rows.append([
            i,
            photo_val,
            p.name,
            p.phone,
            p.email,
            p.address,
            p.get_gender_display(),
            p.date_of_birth.strftime('%Y-%m-%d') if p.date_of_birth else "",
            p.chief_complaint,
            f"{p.progress_percentage}%",
            p.registered_date.strftime('%Y-%m-%d')
        ])
    return rows

@login_required
def export_patients_excel(request):
    patients, _ = _get_filtered_patients(request)
    headers = ["S.No", "Photo", "Name", "Phone", "Email", "Address", "Gender", "DOB", "Chief Complaint", "Progress", "Registered"]
    rows = _get_patient_export_rows(patients)
    return SpinalCureExport.to_excel(rows, headers, lambda r: r, "Patients", "patients", image_cols=[1])

@login_required
def export_patients_csv(request):
    patients, _ = _get_filtered_patients(request)
    headers = ["S.No", "Photo URL", "Name", "Phone", "Email", "Address", "Gender", "DOB", "Chief Complaint", "Progress", "Registered"]
    rows = []
    for i, p in enumerate(patients, 1):
        rows.append([
            i,
            request.build_absolute_uri(p.photo.url) if p.photo else "",
            p.name,
            p.phone,
            p.email,
            p.address,
            p.get_gender_display(),
            p.date_of_birth.strftime('%Y-%m-%d') if p.date_of_birth else "",
            p.chief_complaint,
            f"{p.progress_percentage}%",
            p.registered_date.strftime('%Y-%m-%d')
        ])
    return SpinalCureExport.to_csv(rows, headers, lambda r: r, "patients")

@login_required
def export_patients_pdf(request):
    patients, query = _get_filtered_patients(request)

    headers = [
        "S.No", "Photo", "Name", "Phone", "Email",
        "Address", "Gender", "DOB",
        "Chief Complaint", "Progress", "Registered"
    ]

    rows = []

    for i, p in enumerate(patients, 1):
        rows.append([
            i,
            p.photo.path if p.photo and os.path.exists(p.photo.path) else "",
            p.name,
            p.phone,
            p.email,
            p.address,
            p.get_gender_display(),
            p.date_of_birth.strftime('%Y-%m-%d') if p.date_of_birth else "",
            p.chief_complaint,
            f"{p.progress_percentage}%",
            p.registered_date.strftime('%Y-%m-%d')
        ])

    title = f"Patients List {'(Filtered)' if query else ''}"

    return SpinalCureExport.to_pdf(
        rows,
        headers,
        lambda r: r,
        title,
        "patients",
        orientation='landscape',
        image_cols=[1]   # IMPORTANT: Photo column index is 1
    )

@login_required
def export_patients_copy(request):
    patients, _ = _get_filtered_patients(request)
    headers = ["S.No", "Name", "Phone", "Email", "Address", "Complaint", "Progress"]
    rows = []
    for i, p in enumerate(patients, 1):
        rows.append([i, p.name, p.phone, p.email, p.address, p.chief_complaint, f"{p.progress_percentage}%"])
    text = SpinalCureExport.to_text(rows, headers, lambda r: r)
    return HttpResponse(text, content_type='text/plain')

@login_required
def export_patients_print(request):
    patients, query = _get_filtered_patients(request)
    headers = ["S.No", "Photo", "Name", "Phone", "Email", "Address", "Gender", "DOB", "Chief Complaint", "Progress", "Registered"]
    rows = [[
        counter, 
        p.photo.url if p.photo else "", 
        p.name, 
        p.phone, 
        p.email,
        p.address,
        p.get_gender_display(), 
        p.date_of_birth.strftime('%Y-%m-%d') if p.date_of_birth else "", 
        p.chief_complaint, 
        f"{p.progress_percentage}%",
        p.registered_date.strftime('%Y-%m-%d')
    ] for counter, p in enumerate(patients, start=1)]
    from datetime import datetime
    context = {
        'clinic': ClinicProfile.objects.first(),
        'rows': rows,
        'title': 'Patients List',
        'query': query,
        'headers': headers,
        'now': datetime.now(),
        'photo_col_index': 1,  # 0-indexed position of "Photo" column
    }
    return render(request, 'exports/print_template.html', context)



@login_required
def patient_detail_view(request, pk):
    """View patient details."""
    if not has_capability(request.user, 'patients.view'):
        messages.error(request, gettext('You do not have permission to view this page.'))
        return redirect('dashboard')
    
    patient = get_object_or_404(Patient.objects.prefetch_related('sessions', 'payments', 'appointments', 'treatment_plans'), pk=pk)
    sessions = patient.sessions.all().select_related('treatment_plan').order_by('-session_number')
    treatment_plans = patient.treatment_plans.all().order_by('-created_at')
    payments = patient.payments.all().order_by('-payment_date')
    total_amount = payments.aggregate(total=Sum('total_amount'))['total'] or 0
    amount_paid = payments.aggregate(paid=Sum('amount_paid'))['paid'] or 0
    remaining_amount = total_amount - amount_paid
    
    import json
    plans_list = [{'value': 'all', 'label': 'All Plans / General'}]
    for p in treatment_plans:
        plans_list.append({'value': str(p.id), 'label': p.name + (' (Inactive)' if not p.is_active else '')})
    treatment_plans_json = json.dumps(plans_list)

    context = {
        'patient': patient,
        'sessions': sessions,
        'treatment_plans': treatment_plans,
        'payments': payments,
        'total_amount': total_amount,
        'amount_paid': amount_paid,
        'remaining_amount': remaining_amount,
        'treatment_plans_json': treatment_plans_json,
    }
    return render(request, 'patients/patient_detail.html', context)


@login_required
def patient_print_card_view(request, pk):
    """Print patient card."""
    if not has_capability(request.user, 'patients.view'):
        messages.error(request, gettext('You do not have permission to print this.'))
        return redirect('dashboard')
    
    patient = get_object_or_404(Patient, pk=pk)
    context = {'patient': patient}
    return render(request, 'patients/print/patient_card.html', context)


@login_required
def reviews_list_view(request):
    """Admin view for managing all patient reviews."""
    if not (request.user.role == 'superadmin' or request.user.is_superuser):
        messages.error(request, gettext('Only admins can manage reviews.'))
        return redirect('dashboard')
    
    query = request.GET.get('q', '')
    reviews = PatientReview.objects.all().select_related('patient', 'practitioner').order_by('-created_at')
    if query:
        from .search import patient_q
        reviews = reviews.filter(patient_q(query, 'patient__', ('name',)) | Q(review_text__icontains=query))
    
    avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0
    
    # Export URLs
    base_export_params = f"?q={query}" if query else ""
    from django.urls import reverse
    
    context = {
        'reviews': reviews,
        'avg_rating': round(avg_rating, 1) if avg_rating else 0,
        'total_reviews': reviews.count(),
        'published': reviews.filter(is_published=True).count(),
        'search_query': query,
        'export_reviews_excel_url': reverse('export-reviews-excel') + base_export_params,
        'export_reviews_csv_url': reverse('export-reviews-csv') + base_export_params,
        'export_reviews_pdf_url': reverse('export_reviews_pdf') + base_export_params,
        'export_reviews_copy_url': reverse('export_reviews_copy') + base_export_params,
        'export_reviews_print_url': reverse('export_reviews_print') + base_export_params,
    }
    return render(request, 'patients/reviews.html', context)


@login_required
def review_toggle_publish(request, pk):
    """Toggle the published status of a review."""
    if not (request.user.role == 'superadmin' or request.user.is_superuser):
        messages.error(request, gettext('Only admins can manage reviews.'))
        return redirect('dashboard')
    
    review = get_object_or_404(PatientReview, pk=pk)
    review.is_published = not review.is_published
    review.save()
    status = 'published' if review.is_published else 'unpublished'
    messages.success(request, gettext('Review by %(name)s has been %(status)s.') % {'name': review.patient.name, 'status': status})
    logger.info(f'Review {pk} was {status} by {request.user.email}')
    return redirect('patient-reviews')


@login_required
def review_create_view(request):
    """Add a new review from the admin panel."""
    if not (request.user.role == 'superadmin' or request.user.is_superuser):
        messages.error(request, gettext('Only admins can create reviews.'))
        return redirect('dashboard')
    
    from clinic.models import Practitioner
    
    if request.method == 'POST':
        patient_id = request.POST.get('patient')
        practitioner_id = request.POST.get('practitioner')
        rating = int(request.POST.get('rating', 5))
        review_text = request.POST.get('review_text', '')
        is_published = request.POST.get('is_published') == 'on'
        
        patient = get_object_or_404(Patient, pk=patient_id)
        practitioner = Practitioner.objects.filter(pk=practitioner_id).first()
        
        PatientReview.objects.create(
            patient=patient,
            practitioner=practitioner,
            rating=rating,
            review_text=review_text,
            is_published=is_published,
        )
        
        messages.success(request, gettext('Review for %(name)s added.') % {'name': patient.name})
        logger.info(f'New review created for patient {patient_id} by {request.user.email}')
        return redirect('patient-reviews')
    
    context = {
        'patients': Patient.objects.all().order_by('name'),
        'practitioners': Practitioner.objects.filter(is_active=True),
    }
    return render(request, 'patients/review_form.html', context)
    return render(request, 'patients/review_form.html', context)


@login_required
def patient_create_view(request):
    """Create a new patient."""
    if not has_capability(request.user, 'patients.edit'):
        messages.error(request, gettext('You do not have permission to add patients.'))
        return redirect('patient-list')
    
    if request.method == 'POST':
        try:
            handled_by_id = request.POST.get('handled_by')
            handled_by = Practitioner.objects.filter(id=handled_by_id).first() if handled_by_id else None
            patient_id_str = request.POST.get('patient_id_str')
            if not patient_id_str:
                patient_id_str = None
                
            patient = Patient.objects.create(
                patient_id_str=patient_id_str,
                registration_number=request.POST.get('registration_number', ''),
                whatsapp_no=request.POST.get('whatsapp_no', ''),
                reason_for_visit=request.POST.get('reason_for_visit', ''),
                name=request.POST.get('name'),
                phone=request.POST.get('phone'),
                email=request.POST.get('email', ''),
                address=request.POST.get('address', ''),
                gender=request.POST.get('gender', ''),
                date_of_birth=request.POST.get('date_of_birth') or None,
                attender_name=request.POST.get('attender_name', ''),
                attender_phone=request.POST.get('attender_phone', ''),
                attender_relation=request.POST.get('attender_relation', ''),
                chief_complaint=request.POST.get('chief_complaint', ''),
                medical_history=request.POST.get('medical_history', ''),
                allergies=request.POST.get('allergies', ''),
                total_sittings=int(request.POST.get('total_sittings', 0) or 0),
                notes=request.POST.get('notes', ''),
                is_active=request.POST.get('is_active') == 'on',
                handled_by=handled_by
            )
            
            # Save Acupuncture Diagnosis Data
            import json
            from .models import AcupunctureDiagnosis
            diagnosis_str = request.POST.get('diagnosis_data', '{}')
            try:
                diagnosis_data = json.loads(diagnosis_str)
            except:
                diagnosis_data = {}
            AcupunctureDiagnosis.objects.create(patient=patient, diagnosis_data=diagnosis_data)
            if patient.total_sittings > 0:
                from .models import TreatmentPlan
                TreatmentPlan.objects.create(
                    patient=patient,
                    name='Initial Treatment Plan',
                    chief_complaint=patient.chief_complaint,
                    total_sittings=patient.total_sittings,
                    is_active=True
                )
                
            if request.FILES.get('photo'):
                patient.photo = request.FILES['photo']
                patient.save()
            log_action(request, 'create', 'Patient', patient.name, object_id=patient.id)
            messages.success(request, gettext('Patient %(name)s registered successfully.') % {'name': patient.name})
            return redirect('patient-detail', pk=patient.id)
        except Exception as e:
            messages.error(request, gettext('Error creating patient: %(value1)s') % {'value1': str(e)})
            
    initial_name = request.GET.get('name', '')
    initial_phone = request.GET.get('phone', '')
            
    practitioners = Practitioner.objects.filter(is_active=True)
    return render(request, 'patients/patient_form.html', {
        'patient': None,
        'practitioners': practitioners,
        'initial_name': initial_name,
        'initial_phone': initial_phone
    })


@login_required
@require_pin_auth('patient-list')
def patient_edit_view(request, pk):
    """Edit an existing patient."""
    if not has_capability(request.user, 'patients.edit'):
        messages.error(request, gettext('You do not have permission to edit patients.'))
        return redirect('patient-list')
    
    patient = get_object_or_404(Patient, pk=pk)
    
    if request.method == 'POST':
        try:
            changes = {}
            raw_changes = {}
            
            def update_field(field_name, db_field_name, old_val, new_val):
                old_s = "" if old_val is None else str(old_val).strip()
                new_s = "" if new_val is None else str(new_val).strip()
                if old_s != new_s:
                    changes[field_name] = {"old": old_s, "new": new_s}
                    # We store the primitive/raw value for programmatic revert
                    # If it's a model instance, store its ID
                    raw_old = old_val.pk if hasattr(old_val, 'pk') else old_val
                    raw_changes[db_field_name] = raw_old
                    return new_val
                return old_val

            handled_by_id = request.POST.get('handled_by')
            new_handled_by = Practitioner.objects.filter(id=handled_by_id).first() if handled_by_id else None
            patient.handled_by = update_field('Practitioner', 'handled_by_id', patient.handled_by, new_handled_by)
            
            patient.name = update_field('Name', 'name', patient.name, request.POST.get('name', patient.name))
            
            new_patient_id = request.POST.get('patient_id_str') or None
            patient.patient_id_str = update_field('Patient ID', 'patient_id_str', patient.patient_id_str, new_patient_id)
            patient.registration_number = update_field('Regd No', 'registration_number', patient.registration_number, request.POST.get('registration_number', patient.registration_number))
            patient.whatsapp_no = update_field('Whatsapp No', 'whatsapp_no', patient.whatsapp_no, request.POST.get('whatsapp_no', patient.whatsapp_no))
            patient.reason_for_visit = update_field('Reason For Visit', 'reason_for_visit', patient.reason_for_visit, request.POST.get('reason_for_visit', patient.reason_for_visit))
            
            patient.phone = update_field('Phone', 'phone', patient.phone, request.POST.get('phone', patient.phone))
            patient.email = update_field('Email', 'email', patient.email, request.POST.get('email', patient.email))
            patient.address = update_field('Address', 'address', patient.address, request.POST.get('address', patient.address))
            patient.gender = update_field('Gender', 'gender', patient.gender, request.POST.get('gender', patient.gender))
            
            new_dob = request.POST.get('date_of_birth')
            patient.date_of_birth = update_field('Date of Birth', 'date_of_birth', patient.date_of_birth, new_dob if new_dob else patient.date_of_birth)
            
            patient.attender_name = update_field('Attender Name', 'attender_name', patient.attender_name, request.POST.get('attender_name', patient.attender_name))
            patient.attender_phone = update_field('Attender Phone', 'attender_phone', patient.attender_phone, request.POST.get('attender_phone', patient.attender_phone))
            patient.attender_relation = update_field('Attender Relation', 'attender_relation', patient.attender_relation, request.POST.get('attender_relation', patient.attender_relation))
            patient.chief_complaint = update_field('Chief Complaint', 'chief_complaint', patient.chief_complaint, request.POST.get('chief_complaint', patient.chief_complaint))
            patient.medical_history = update_field('Medical History', 'medical_history', patient.medical_history, request.POST.get('medical_history', patient.medical_history))
            patient.allergies = update_field('Allergies', 'allergies', patient.allergies, request.POST.get('allergies', patient.allergies))
            
            new_sittings = int(request.POST.get('total_sittings', patient.total_sittings) or 0)
            patient.total_sittings = update_field('Total Sittings', 'total_sittings', patient.total_sittings, new_sittings)
            
            patient.notes = update_field('Notes', 'notes', patient.notes, request.POST.get('notes', patient.notes))
            
            import json
            from .models import AcupunctureDiagnosis
            diagnosis_str = request.POST.get('diagnosis_data')
            if diagnosis_str is not None:
                try:
                    diagnosis_data = json.loads(diagnosis_str)
                    diag, created = AcupunctureDiagnosis.objects.get_or_create(patient=patient)
                    if diag.diagnosis_data != diagnosis_data:
                        diag.diagnosis_data = diagnosis_data
                        diag.save()
                        changes['TCM Diagnosis'] = {"old": "Updated", "new": "Updated"}
                except:
                    pass
            
            new_is_active = request.POST.get('is_active') == 'on'
            patient.is_active = update_field('Status (Active)', 'is_active', patient.is_active, new_is_active)
            
            if request.FILES.get('photo'):
                patient.photo = request.FILES['photo']
                changes['Photo'] = {"old": "Old Photo", "new": "New Photo Uploaded"}
                
            patient.save()
            log_action(request, 'update', 'Patient', patient.name, object_id=patient.id, changes=changes, raw_changes=raw_changes)
            messages.success(request, gettext('Patient %(name)s updated successfully.') % {'name': patient.name})
            return redirect('patient-detail', pk=patient.id)
        except Exception as e:
            messages.error(request, gettext('Error updating patient: %(value1)s') % {'value1': str(e)})
            
    practitioners = Practitioner.objects.filter(is_active=True)
    return render(request, 'patients/patient_form.html', {
        'patient': patient,
        'practitioners': practitioners,
        'initial_name': patient.name,
        'initial_phone': patient.phone,
    })


@login_required
@require_pin_auth('patient-list')
def patient_delete_view(request, pk):
    """Delete a patient profile securely."""
    patient = get_object_or_404(Patient, pk=pk)
    if request.method == 'POST':
        name = patient.name
        patient_id = patient.id
        
        # Capture snapshot for reverting
        from django.core import serializers
        import json
        snapshot = json.loads(serializers.serialize('json', [patient]))[0]
        
        changes = {
            "Record": {"old": f"Patient: {name}", "new": "DELETED"},
            "Phone": {"old": patient.phone, "new": "DELETED"},
            "Email": {"old": patient.email, "new": "DELETED"}
        }
        
        patient.delete()
        log_action(request, 'delete', 'Patient', name, object_id=patient_id, changes=changes, snapshot=snapshot)
        
        # Determine redirect logic: If Ajax, return JSON response
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
            return JsonResponse({'status': 'ok', 'redirect_url': '/en/patients/'})
            
        messages.success(request, gettext('Patient %(name)s has been deleted.') % {'name': name})
        return redirect('patient-list')
        
    return redirect('patient-detail', pk=pk)


@login_required
def review_delete_view(request, pk):
    review = get_object_or_404(PatientReview, pk=pk)
    if request.method == 'POST':
        review.delete()
        messages.success(request, gettext('Review deleted.'))
    return redirect('patient-reviews')


@login_required
def session_create_view(request, patient_pk):
    """Add a new treatment session for a specific patient."""
    if not has_capability(request.user, 'clinical.edit'):
        messages.error(request, gettext('You do not have permission to add sessions.'))
        return redirect('dashboard')
        
    patient = get_object_or_404(Patient, pk=patient_pk)
    practitioners = Practitioner.objects.filter(is_active=True).order_by('name')
    
    if request.method == 'POST':
        try:
            consulted_by_id = request.POST.get('consulted_by')
            session_date = request.POST.get('session_date')
            session_time = request.POST.get('session_time') or None
            duration_minutes = int(request.POST.get('duration_minutes', 30) or 30)
            acupoints_used = request.POST.get('acupoints_used')
            techniques_used = request.POST.get('techniques_used', '')
            patient_feedback = request.POST.get('patient_feedback', '')
            practitioner_notes = request.POST.get('practitioner_notes', '')
            next_appointment_date = request.POST.get('next_appointment_date') or None
            pain_scale = int(request.POST.get('pain_scale', 5) or 5)
            mobility_score = int(request.POST.get('mobility_score', 3) or 3)
            treatment_plan_id = request.POST.get('treatment_plan')
            
            practitioner = None
            if consulted_by_id:
                practitioner = Practitioner.objects.filter(pk=consulted_by_id).first()
                
            treatment_plan = None
            if treatment_plan_id:
                from .models import TreatmentPlan
                treatment_plan = TreatmentPlan.objects.filter(pk=treatment_plan_id).first()
                
            session = Session.objects.create(
                patient=patient,
                consulted_by=practitioner,
                session_date=session_date,
                session_time=session_time,
                duration_minutes=duration_minutes,
                acupoints_used=acupoints_used,
                techniques_used=techniques_used,
                patient_feedback=patient_feedback,
                practitioner_notes=practitioner_notes,
                next_appointment_date=next_appointment_date,
                pain_scale=pain_scale,
                mobility_score=mobility_score,
                treatment_plan=treatment_plan
            )
            
            # The session_number is auto-incremented in Session.save()
            session.save()
            
            messages.success(request, gettext('Session #%(session_number)s recorded successfully.') % {'session_number': session.session_number})
            return redirect('patient-detail', pk=patient.id)
            
        except Exception as e:
            messages.error(request, gettext('Error creating session: %(value1)s') % {'value1': str(e)})
            
    treatment_plans = patient.treatment_plans.filter(is_active=True).order_by('-created_at')
    context = {
        'patient': patient,
        'practitioners': practitioners,
        'treatment_plans': treatment_plans
    }
    return render(request, 'patients/session_form.html', context)


# ─── Session Security Views ───────────────────────────────────────────────────

@login_required
@require_POST
def session_request_pin_view(request):
    """Generate a 4-digit security PIN and email it to the superadmin for approval."""
    if not has_capability(request.user, 'clinical.edit'):
        return JsonResponse({'status': 'error', 'message': gettext('Permission denied.')}, status=403)

    pin = str(random.randint(1000, 9999))
    request.session['session_security_pin'] = pin
    request.session['session_security_pin_ts'] = timezone.now().isoformat()

    # Find the superadmin's email
    from accounts.models import CustomUser
    superadmin = CustomUser.objects.filter(is_superuser=True).first()
    if not superadmin:
        superadmin = CustomUser.objects.filter(role='superadmin').first()

    requester_name = request.user.get_full_name() or request.user.email
    requester_role = request.user.get_role_display() if hasattr(request.user, 'get_role_display') else 'Staff'
    # Read context from POST if provided, fallback to session
    target_name = request.POST.get('target_name', 'a sensitive record')
    action_type = request.POST.get('action_type', 'modify')
    record_type = request.POST.get('record_type', 'sensitive')
    
    # Capitalize action
    if action_type == 'delete':
        action_desc = f"Deleting {target_name}"
    elif action_type == 'edit':
        action_desc = f"Editing {target_name}"
    else:
        action_desc = f"Modifying {target_name}"
        
    action_context = request.session.get('pending_action_context', action_desc)

    now_str = timezone.now().strftime('%d %b %Y, %I:%M %p')

    # Send ONLY to superadmin, do not CC the requesting staff member (security risk)
    admin_email = superadmin.email if superadmin else None
    
    if not admin_email:
        # Fallback to a system default admin email or fail
        admin_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'admin@spinalcure.com')
        
    recipients = [admin_email]

    try:
        from django.template.loader import render_to_string
        from django.core.mail import EmailMultiAlternatives
        
        subject = f'🔐 SpinalCure — Authorization Request for {target_name}'
        
        # Plain text fallback
        text_message = (
            f'AUTHORIZATION REQUEST\n'
            f'{"="*50}\n\n'
            f'Staff Member : {requester_name} ({requester_role})\n'
            f'Email        : {request.user.email}\n'
            f'Requested At : {now_str}\n'
            f'Action       : {action_context}\n\n'
            f'{"="*50}\n\n'
            f'Your approval PIN is:\n\n'
            f'        *** {pin} ***\n\n'
            f'This PIN is valid for 5 minutes. Share it with the staff member ONLY if you approve this action.\n'
            f'If you did NOT expect this request, please investigate immediately.\n\n'
            f'— SpinalCure Security System'
        )
        
        # HTML Template
        context = {
            'staff_name': requester_name,
            'staff_role': requester_role,
            'staff_email': request.user.email,
            'requested_at': now_str,
            'action_context': action_context,
            'target_name': target_name,
            'action_type': action_type.capitalize(),
            'record_type': record_type,
            'pin': pin,
        }
        html_message = render_to_string('emails/auth_request.html', context, request=request)
        
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@spinalcure.com'),
            to=recipients,
        )
        msg.attach_alternative(html_message, "text/html")
        msg.send(fail_silently=False)
        logger.info(f'Admin authorization PIN sent to {admin_email} for {request.user.email} | action: {action_context}')
        masked = admin_email[:3] + '****' + admin_email[admin_email.index('@'):]
        return JsonResponse({'status': 'sent', 'email': masked})
    except Exception as e:
        logger.error(f'Failed to send admin authorization PIN: {e}')
        return JsonResponse({'status': 'error', 'message': gettext('Failed to send PIN. Check email settings.')}, status=500)


@login_required
@require_POST
def session_verify_pin_view(request):
    """Validate the submitted PIN and issue a one-time authorization token."""
    submitted_pin = request.POST.get('pin', '').strip()
    stored_pin = request.session.get('session_security_pin')
    stored_ts_str = request.session.get('session_security_pin_ts')

    if not stored_pin or not stored_ts_str:
        return JsonResponse({'status': 'error', 'message': gettext('No PIN was requested. Please request a new PIN.')}, status=400)

    # Check expiry (5 minutes)
    stored_ts = datetime.fromisoformat(stored_ts_str)
    if timezone.now() - stored_ts > timedelta(minutes=5):
        del request.session['session_security_pin']
        del request.session['session_security_pin_ts']
        return JsonResponse({'status': 'expired', 'message': gettext('PIN has expired. Please request a new one.')}, status=400)

    if submitted_pin != stored_pin:
        return JsonResponse({'status': 'invalid', 'message': gettext('Incorrect PIN. Please try again.')}, status=400)

    # PIN is correct — issue a one-time token
    token = secrets.token_urlsafe(24)
    request.session['session_security_token'] = token
    request.session['session_security_pin'] = None  # Invalidate PIN after use
    logger.info(f'Security PIN verified for {request.user.email}')
    return JsonResponse({'status': 'ok', 'token': token})


@login_required
def session_edit_view(request, patient_pk, session_pk):
    """Edit a treatment session — requires prior PIN authorization."""
    if not has_capability(request.user, 'clinical.edit'):
        messages.error(request, gettext('You do not have permission to edit sessions.'))
        return redirect('dashboard')

    session = get_object_or_404(Session, pk=session_pk, patient__pk=patient_pk)
    patient = session.patient
    practitioners = Practitioner.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        try:
            consulted_by_id = request.POST.get('consulted_by')
            session.consulted_by = Practitioner.objects.filter(pk=consulted_by_id).first() if consulted_by_id else None
            session.session_date = request.POST.get('session_date')
            session.session_time = request.POST.get('session_time') or None
            session.duration_minutes = int(request.POST.get('duration_minutes', 30) or 30)
            session.acupoints_used = request.POST.get('acupoints_used')
            session.techniques_used = request.POST.get('techniques_used', '')
            session.patient_feedback = request.POST.get('patient_feedback', '')
            session.practitioner_notes = request.POST.get('practitioner_notes', '')
            session.next_appointment_date = request.POST.get('next_appointment_date') or None
            session.pain_scale = int(request.POST.get('pain_scale', 5) or 5)
            session.mobility_score = int(request.POST.get('mobility_score', 3) or 3)
            
            treatment_plan_id = request.POST.get('treatment_plan')
            if treatment_plan_id:
                from .models import TreatmentPlan
                session.treatment_plan = TreatmentPlan.objects.filter(pk=treatment_plan_id).first()
            else:
                session.treatment_plan = None
                
            session.save()
            log_action(request, 'update', 'Session', f'Session #{session.session_number} — {session.patient.name}', object_id=session_pk)
            logger.info(f'Session {session_pk} edited by {request.user.email}')
            messages.success(request, gettext('Session #%(session_number)s updated successfully.') % {'session_number': session.session_number})
            return redirect('patient-detail', pk=patient.id)

        except Exception as e:
            messages.error(request, gettext('Error updating session: %(value1)s') % {'value1': str(e)})

    btn_token = request.GET.get('auth_token', '')
    treatment_plans = patient.treatment_plans.filter(is_active=True).order_by('-created_at')

    context = {
        'session': session,
        'patient': patient,
        'practitioners': practitioners,
        'treatment_plans': treatment_plans,
        'auth_token': btn_token,
    }
    return render(request, 'patients/session_edit.html', context)


@login_required
@require_POST
@require_pin_auth('patient-list')
def session_delete_view(request, patient_pk, session_pk):
    """Delete a treatment session."""
    session = get_object_or_404(Session, pk=session_pk, patient__pk=patient_pk)
    patient = session.patient

    session_num = session.session_number
    session.delete()
    log_action(request, 'delete', 'Session', f'Session #{session_num} — {patient.name}', object_id=session_pk)
    logger.info(f'Session #{session_num} for patient {patient_pk} deleted by {request.user.email}')
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
        return JsonResponse({'status': 'ok', 'message': gettext('Session #%(session_num)s deleted.') % {'session_num': session_num}})
        
    messages.success(request, gettext('Session #%(session_num)s has been permanently deleted.') % {'session_num': session_num})
    return redirect('patient-detail', pk=patient.id)

def _get_filtered_reviews(request):
    query = request.GET.get('q', '')
    reviews = PatientReview.objects.select_related('patient', 'practitioner').all().order_by('-created_at')
    if query:
        from .search import patient_q
        reviews = reviews.filter(patient_q(query, 'patient__', ('name',)) | Q(review_text__icontains=query))
    return reviews, query

def _review_mapping(r):
    return [r.patient.name, r.practitioner.name if r.practitioner else "General", r.rating, r.review_text, "Published" if r.is_published else "Hidden", r.created_at.strftime('%Y-%m-%d')]

@login_required
def export_reviews_excel(request):
    reviews, _ = _get_filtered_reviews(request)
    headers = ["Patient", "Practitioner", "Rating", "Review", "Status", "Date"]
    return SpinalCureExport.to_excel(reviews, headers, _review_mapping, "Reviews", "reviews")

@login_required
def export_reviews_csv(request):
    reviews, _ = _get_filtered_reviews(request)
    headers = ["Patient", "Practitioner", "Rating", "Review", "Status", "Date"]
    return SpinalCureExport.to_csv(reviews, headers, _review_mapping, "reviews")

@login_required
def export_reviews_pdf(request):
    reviews, query = _get_filtered_reviews(request)
    headers = ["Patient", "Rating", "Review", "Status", "Date"]
    def pdf_mapping(r):
        return [r.patient.name, r.rating, (r.review_text[:50] + '...') if len(r.review_text) > 50 else r.review_text, "Published" if r.is_published else "Hidden", r.created_at.strftime('%Y-%m-%d')]
    title = f"Patient Reviews {'(Filtered)' if query else ''}"
    return SpinalCureExport.to_pdf(reviews, headers, pdf_mapping, title, "reviews")

@login_required
def export_reviews_copy(request):
    reviews, _ = _get_filtered_reviews(request)
    headers = ["Patient", "Rating", "Review", "Status", "Date"]
    text = SpinalCureExport.to_text(reviews, headers, _review_mapping)
    from django.http import HttpResponse
    return HttpResponse(text, content_type='text/plain')

@login_required
def export_reviews_print(request):
    reviews, query = _get_filtered_reviews(request)
    headers = ["Patient", "Rating", "Review", "Status", "Date"]
    rows = [_review_mapping(r) for r in reviews]
    from datetime import datetime
    context = {
        'rows': rows,
        'title': 'Reviews Report',
        'query': query,
        'headers': headers,
        'now': datetime.now(),
    }
    return render(request, 'exports/print_template.html', context)


# ── Patient Portal (Self-Service) ─────────────────────────────────────────

def patient_login_view(request):
    """Patient enters their phone number; a one-time code is emailed if the record exists."""
    if 'patient_id' in request.session:
        return redirect('portal_dashboard')

    if request.method == 'POST':
        from . import portal_auth
        if not portal_auth.request_code(request, request.POST.get('phone', '').strip()):
            messages.error(request, gettext('Too many attempts. Please try again later.'))
            return render(request, 'patients/portal/login.html', status=429)
        # Identical outcome whether or not the number is registered.
        messages.info(request, gettext('If this number is registered and has an email on file, a code has been sent.'))
        return redirect('portal_verify')

    return render(request, 'patients/portal/login.html')


def patient_verify_otp_view(request):
    """Verify the emailed one-time code and start the patient session."""
    if 'patient_id' in request.session:
        return redirect('portal_dashboard')

    from . import portal_auth
    if not portal_auth.pending_login(request):
        return redirect('portal_login')

    if request.method == 'POST':
        if portal_auth.verify_code(request, request.POST.get('otp', '')):
            return redirect('portal_dashboard')
        messages.error(request, gettext('Invalid or expired code. Please try again.'))
        if not portal_auth.pending_login(request):
            return redirect('portal_login')

    return render(request, 'patients/portal/verify.html')


def patient_logout_view(request):
    """Logout patient."""
    if 'patient_id' in request.session:
        del request.session['patient_id']
    return redirect('portal_login')


def patient_dashboard_view(request):
    """Main self-service dashboard for the patient."""
    patient_id = request.session.get('patient_id')
    if not patient_id:
        return redirect('portal_login')
        
    patient = get_object_or_404(Patient, id=patient_id)
    
    # Upcoming appointments
    from appointments.models import Appointment
    upcoming_appointments = Appointment.objects.filter(
        patient=patient, 
        appointment_date__gte=date.today()
    ).order_by('appointment_date', 'appointment_time')
    
    # Session history
    from .models import Session
    sessions = Session.objects.filter(patient=patient).order_by('-session_date')
    
    # Payment history
    from payments.models import Payment
    payments = Payment.objects.filter(patient=patient).order_by('-payment_date')
    
    context = {
        'patient': patient,
        'upcoming_appointments': upcoming_appointments,
        'sessions': sessions,
        'payments': payments,
        'clinic': ClinicProfile.objects.first(),
    }
    return render(request, 'patients/portal/dashboard.html', context)


@require_capability('clinical.view')
def session_pdf_view(request, session_pk):
    """Generate professional PDF clinical note for a session."""
    from clinic.models import ClinicProfile
    session = get_object_or_404(Session, pk=session_pk)
    clinic = ClinicProfile.objects.first()
    
    context = {
        'session': session,
        'clinic': clinic,
    }
    
    filename = f"Session_{session.session_number}_{session.patient.name.replace(' ', '_')}.pdf"
    response = SpinalCureExport.render_to_pdf('patients/print/session_note_pdf.html', context)
    
    if response:
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
    
    messages.error(request, gettext("Failed to generate PDF. Please contact support."))
    return redirect('patient-detail', pk=session.patient.id)

# ---------------------------------------------------------------------------
# Treatment Plan Views
# ---------------------------------------------------------------------------

@login_required
@require_POST
def treatment_plan_create_view(request, patient_pk):
    """Create a new treatment plan for a patient."""
    if not has_capability(request.user, 'clinical.edit'):
        messages.error(request, gettext('You do not have permission to perform this action.'))
        return redirect('dashboard')
        
    patient = get_object_or_404(Patient, pk=patient_pk)
    
    try:
        name = request.POST.get('name')
        chief_complaint = request.POST.get('chief_complaint', '')
        total_sittings = int(request.POST.get('total_sittings', 0) or 0)
        is_active = request.POST.get('is_active') == 'on'
        
        plan = TreatmentPlan.objects.create(
            patient=patient,
            name=name,
            chief_complaint=chief_complaint,
            total_sittings=total_sittings,
            is_active=is_active
        )
        
        # Optionally, deactivate all other plans if this one is active
        # if is_active:
        #    TreatmentPlan.objects.filter(patient=patient).exclude(pk=plan.pk).update(is_active=False)
            
        messages.success(request, gettext("Treatment plan '%(name)s' created successfully.") % {'name': name})
    except Exception as e:
        messages.error(request, gettext('Error creating treatment plan: %(value1)s') % {'value1': str(e)})
        
    return redirect('patient-detail', pk=patient.id)

@login_required
@require_POST
def treatment_plan_edit_view(request, patient_pk, plan_pk):
    """Edit an existing treatment plan."""
    if not has_capability(request.user, 'clinical.edit'):
        return JsonResponse({'status': 'error', 'message': gettext('Permission denied.')}, status=403)
        
    plan = get_object_or_404(TreatmentPlan, pk=plan_pk, patient_id=patient_pk)
    
    try:
        plan.name = request.POST.get('name', plan.name)
        plan.chief_complaint = request.POST.get('chief_complaint', plan.chief_complaint)
        plan.total_sittings = int(request.POST.get('total_sittings', plan.total_sittings) or plan.total_sittings)
        plan.is_active = request.POST.get('is_active') == 'on'
        plan.save()
        
        messages.success(request, gettext("Treatment plan '%(name)s' updated successfully.") % {'name': plan.name})
    except Exception as e:
        messages.error(request, gettext('Error updating treatment plan: %(value1)s') % {'value1': str(e)})
        
    return redirect('patient-detail', pk=patient_pk)

@login_required
@require_POST
def treatment_plan_delete_view(request, patient_pk, plan_pk):
    """Delete a treatment plan."""
    if not has_capability(request.user, 'clinical.edit'):
        return JsonResponse({'status': 'error', 'message': gettext('Permission denied.')}, status=403)
        
    plan = get_object_or_404(TreatmentPlan, pk=plan_pk, patient_id=patient_pk)
    
    # Check if there are sessions linked
    if plan.sessions.exists():
        messages.error(request, gettext("Cannot delete plan '%(name)s' because it has sessions attached. Move or delete them first.") % {'name': plan.name})
    else:
        plan.delete()
        messages.success(request, gettext('Treatment plan deleted successfully.'))
        
    return redirect('patient-detail', pk=patient_pk)
