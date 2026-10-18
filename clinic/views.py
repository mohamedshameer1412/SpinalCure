from django.utils.translation import gettext
from django.shortcuts import render, get_object_or_404, redirect
from django_ratelimit.decorators import ratelimit
from patients.search import patient_q
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated, SAFE_METHODS
from spinalcure.rbac import capability_permission, has_capability, require_capability
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ClinicProfile, Practitioner
from patients.models import PatientReview, Patient
from appointments.models import Appointment
from events.models import Event, EventRegistration, EventFeedback
from events.models import Event, EventRegistration, EventFeedback
from .serializers import ClinicProfileSerializer, PractitionerSerializer
from spinalcure.permissions import IsSuperAdmin, IsDoctor
import json
import logging
from spinalcure.utils import decode_b64uuid

logger = logging.getLogger(__name__)


def clinic_portfolio_view(request):
    """Public clinic portfolio single-page view."""
    clinic = ClinicProfile.objects.first()
    if not clinic:
        return render(request, 'clinic/portfolio_spa.html', {
            'clinic': None,
            'practitioners': [],
            'reviews': [],
            'avg_rating': 0,
            'rating_range': range(1, 6)
        })

    # Fetch active practitioners for this clinic
    practitioners = Practitioner.objects.filter(is_active=True)
    
    # Fetch published reviews
    reviews = PatientReview.objects.filter(is_published=True).order_by('-created_at')[:6]
    
    # Calculate average rating
    avg_rating = 0
    if reviews.exists():
        total_rating = sum([r.rating for r in reviews])
        avg_rating = total_rating / reviews.count()

    # Fetch published events
    events = Event.objects.filter(is_published=True).order_by('date', 'start_time')

    # Fetch published courses
    from courses.models import Course
    courses = Course.objects.filter(is_published=True).order_by('-created_at')

    # Fetch published admin-curated testimonials
    from .models import ClinicTestimonial
    testimonials = ClinicTestimonial.objects.filter(
        clinic=clinic, is_published=True
    ).order_by('display_order', '-created_at')

    return render(request, 'clinic/portfolio_spa.html', {
        'clinic': clinic,
        'practitioners': practitioners,
        'reviews': reviews,
        'events': events,
        'courses': courses,
        'testimonials': testimonials,
        'avg_rating': avg_rating,
        'rating_range': range(1, 6)
    })

def clinic_about_page_view(request):
    """Dedicated About Us page."""
    clinic = ClinicProfile.objects.first()
    return render(request, 'clinic/about_page.html', {
        'clinic': clinic
    })


def practitioner_detail_view(request, pk):
    """Public practitioner detail view."""
    practitioner = get_object_or_404(Practitioner, pk=pk, is_active=True)
    reviews = PatientReview.objects.filter(practitioner=practitioner, is_published=True)
    return render(request, 'clinic/practitioner_portfolio.html', {
        'practitioner': practitioner,
        'reviews': reviews,
        'rating_range': range(1, 6)
    })


@require_http_methods(["POST"])
def submit_review_ajax(request):
    """AJAX endpoint for submitting reviews from public portal."""
    try:
        data = json.loads(request.body)
        patient_name = data.get('name', '').strip()
        patient_phone = data.get('phone', '').strip()
        practitioner_id = decode_b64uuid(data.get('practitioner_id'))
        rating = data.get('rating')
        review_text = data.get('review', '').strip()

        # Validate required fields
        if not all([patient_name, patient_phone, practitioner_id, rating]):
            return JsonResponse({
                'status': 'error',
                'message': gettext('All fields are required.')
            }, status=400)

        # Validate rating range
        if rating not in [1, 2, 3, 4, 5]:
            return JsonResponse({
                'status': 'error',
                'message': gettext('Invalid rating value.')
            }, status=400)

        # Get or create patient
        patient, _ = Patient.objects.get_or_create(
            phone=patient_phone,
            defaults={'name': patient_name, 'chief_complaint': 'Review submission'}
        )
        
        practitioner = get_object_or_404(Practitioner, id=practitioner_id, is_active=True)
        
        # Create review (unpublished by default)
        PatientReview.objects.create(
            patient=patient,
            practitioner=practitioner,
            rating=int(rating),
            review_text=review_text,
            is_published=False
        )
        
        logger.info(f'New review submitted by {patient_name} for {practitioner.name}')
        
        return JsonResponse({
            'status': 'success',
            'message': gettext('Thank you! Your review has been submitted for approval.')
        })
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': gettext('Invalid JSON.')}, status=400)
    except Exception as e:
        logger.error(f'Error in submit_review_ajax: {str(e)}')
        return JsonResponse({'status': 'error', 'message': gettext('An error occurred. Please try again.')}, status=500)


@require_http_methods(["POST"])
@ratelimit(key='ip', rate='12/h', method='POST', block=True)
def book_appointment_ajax(request):
    """
    Public booking. Always creates a *guest* booking: an anonymous visitor must never be able to
    attach themselves to, or change, an existing patient's record (staff match guests to patients).
    Availability is re-validated server-side under a lock; the picker in the browser is a convenience.
    """
    from datetime import datetime as _dt
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email
    from appointments import scheduling as sch
    from spinalcure.validators import validate_phone_number

    def fail(message, status=400, code='invalid'):
        return JsonResponse({'status': 'error', 'code': code, 'message': message}, status=status)

    try:
        data = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return fail('Invalid JSON.')
    if not isinstance(data, dict):
        return fail('Invalid request.')
    if str(data.get('website', '')).strip():          # honeypot field: humans never fill it
        return JsonResponse({'status': 'success', 'message': gettext('Appointment booked successfully!')})

    name = str(data.get('name', '')).strip()[:120]
    phone = str(data.get('phone', '')).strip()[:20]
    email = str(data.get('email', '')).strip()[:254]
    notes = str(data.get('notes', '')).strip()[:300]
    appt_type = data.get('type', 'physical')
    if len(name) < 2 or not phone:
        return fail('Please enter your name and phone number.')
    try:
        validate_phone_number(phone)
        if email:
            validate_email(email)
        day = _dt.strptime(str(data.get('date', '')), '%Y-%m-%d').date()
        start = _dt.strptime(str(data.get('time', ''))[:5], '%H:%M').time()
    except ValidationError:
        return fail('Please check your phone number and email address.')
    except ValueError:
        return fail('Please choose a valid date and time.')
    if appt_type not in ('physical', 'online'):
        return fail('Invalid appointment type.')

    practitioner = None
    raw = str(data.get('practitioner_id', '')).strip()
    if raw:
        try:
            raw = decode_b64uuid(raw)
        except Exception:
            pass
        practitioner = Practitioner.objects.filter(id=raw, is_active=True).first()
        if practitioner is None:
            return fail('That practitioner is not available.', 404, 'unknown_practitioner')

    request_key = str(data.get('request_key', ''))[:64] or None
    try:
        appt = sch.book(practitioner=practitioner, day=day, start_time=start, appointment_type=appt_type,
                        guest_name=name, guest_phone=phone, guest_email=email, reason=notes,
                        source='public', request_key=request_key)
    except sch.SchedulingError as exc:
        status = 409 if exc.code in ('conflict', 'unavailable') else 429 if exc.code == 'limit' else 400
        return fail(exc.message, status, exc.code)

    logger.info('Public appointment %s booked for %s', appt.pk, day)
    return JsonResponse({
        'status': 'success',
        'message': 'Appointment booked! ' + ('A confirmation email is on its way.' if email else 'Please keep this time free.'),
        'manage_url': request.build_absolute_uri(sch._manage_path(appt)) if email else '',
    })


# --- Course Views ---

def course_detail_view(request, pk):
    """Public course detail page with registration for active batch and social proof feedback."""
    from courses.models import Course
    course = get_object_or_404(Course, pk=pk, is_published=True)
    active_batch = course.active_batch
    clinic = ClinicProfile.objects.first()

    # Fetch ALL published feedback for this course (cross-batch social proof)
    feedbacks = course.feedback.filter(is_published=True).order_by('-submitted_at')
    
    avg_rating = 0
    if feedbacks.exists():
        avg_rating = sum(f.rating for f in feedbacks) / feedbacks.count()
        
    return render(request, 'clinic/course_detail.html', {
        'course': course,
        'clinic': clinic,
        'active_batch': active_batch,
        'feedbacks': feedbacks,
        'avg_rating': round(avg_rating, 1),
        'rating_range': range(1, 6),
    })


class ClinicProfileViewSet(viewsets.ModelViewSet):
    """
    ViewSet for clinic profile management.
    Only super admins can modify clinic details.
    """
    queryset = ClinicProfile.objects.all()
    serializer_class = ClinicProfileSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]


class PractitionerViewSet(viewsets.ModelViewSet):
    """
    ViewSet for practitioner management.
    Doctors and admins can create/modify practitioners.
    Public can view active practitioners via read-only access.
    """
    queryset = Practitioner.objects.all()
    serializer_class = PractitionerSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filterset_fields = ['is_active', 'gender']
    search_fields = ['name', 'specialization', 'designation_tag', 'qualifications']
    
    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticatedOrReadOnly()]
        return [IsAuthenticated(), capability_permission('users.manage')()]

    def get_queryset(self):
        # Only people who manage the team see inactive practitioners; everyone else sees the public roster.
        if not has_capability(self.request.user, 'users.manage'):
            return Practitioner.objects.filter(is_active=True)
        return Practitioner.objects.all()

# ── Admin Global Search ───────────────────────────────────────────────────

from django.contrib.auth.decorators import login_required
from patients.models import Patient
from appointments.models import Appointment
from django.db.models import Q
from django.urls import reverse

@require_capability('patients.view')
def global_search_ajax(request):
    """Fast AJAX search for top nav bar (Admin only)"""
    query = request.GET.get('q', '').strip()
    if not query or len(query) < 2:
        return JsonResponse({'results': []})

    results = []

    # Search Patients
    patients = Patient.objects.filter(patient_q(query, '', ('name', 'phone', 'email')))[:5]
    for p in patients:
        results.append({
            'type': 'Patient',
            'title': p.name,
            'subtitle': p.phone,
            'url': reverse('patient-detail', args=[p.id]),
            'icon': 'bi-person'
        })

    # Search Appointments
    appointments = Appointment.objects.filter(
        patient_q(query, 'patient__', ('name',)) |
        Q(reason__icontains=query)
    ).select_related('patient')[:5]
    for a in appointments:
        results.append({
            'type': 'Appointment',
            'title': f"{a.patient.name} - {a.get_status_display()}",
            'subtitle': f"{a.appointment_date} at {a.appointment_time.strftime('%I:%M %p')}",
            'url': reverse('appointment_calendar'),
            'icon': 'bi-calendar-event'
        })

    return JsonResponse({'results': results})
