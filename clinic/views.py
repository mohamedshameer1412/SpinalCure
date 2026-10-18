from django.shortcuts import render, get_object_or_404, redirect
from patients.search import patient_q
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated
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


def event_detail_view(request, pk):
    """Public event detail page with registration and feedback."""
    event = get_object_or_404(Event, pk=pk, is_published=True)
    feedbacks = event.feedbacks.filter(is_published=True)
    registration_count = event.registrations.count()
    clinic = ClinicProfile.objects.first()
    avg_rating = 0
    if feedbacks.exists():
        avg_rating = sum(f.rating for f in feedbacks) / feedbacks.count()
    return render(request, 'clinic/event_detail.html', {
        'event': event,
        'clinic': clinic,
        'feedbacks': feedbacks,
        'registration_count': registration_count,
        'avg_rating': round(avg_rating, 1),
        'rating_range': range(1, 6),
    })


@require_http_methods(["POST"])
def register_for_event_ajax(request, pk):
    """AJAX endpoint for event registration."""
    try:
        event = get_object_or_404(Event, pk=pk, is_published=True)
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        phone = data.get('phone', '').strip()
        email = data.get('email', '').strip()
        notes = data.get('notes', '').strip()
        if not name or not phone:
            return JsonResponse({'status': 'error', 'message': 'Name and phone are required.'}, status=400)
        EventRegistration.objects.create(
            event=event, name=name, phone=phone, email=email, notes=notes
        )
        logger.info(f'New registration for event {event.title} by {name}')
        return JsonResponse({'status': 'success', 'message': 'Registration successful! We will be in touch.'})
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid request.'}, status=400)
    except Exception as e:
        logger.error(f'Event registration error: {str(e)}')
        return JsonResponse({'status': 'error', 'message': 'An error occurred. Please try again.'}, status=500)


@require_http_methods(["POST"])
def verify_event_registration_ajax(request, pk):
    """AJAX endpoint to verify if a visitor is registered for this event.
    Returns the registrant's name if found, so the feedback form can be unlocked.
    """
    try:
        event = get_object_or_404(Event, pk=pk, is_published=True)
        if not event.feedback_enabled:
            return JsonResponse({'status': 'error', 'message': 'Feedback is not open for this event.'}, status=403)
        data = json.loads(request.body)
        identifier = data.get('identifier', '').strip()  # phone or email
        if not identifier:
            return JsonResponse({'status': 'error', 'message': 'Please enter your phone number or email.'}, status=400)
        # Look up registration by phone or email (case-insensitive for email)
        from django.db.models import Q
        registration = event.registrations.filter(
            Q(phone=identifier) | Q(email__iexact=identifier)
        ).first()
        if not registration:
            return JsonResponse({
                'status': 'not_found',
                'message': 'No registration found for this event with the provided details. Only registered attendees can leave feedback.'
            }, status=404)
        # Check if they already submitted feedback
        if hasattr(registration, 'feedback'):
            return JsonResponse({
                'status': 'already_submitted',
                'message': 'You have already submitted feedback for this event. Thank you!'
            }, status=409)
        return JsonResponse({
            'status': 'verified',
            'name': registration.name,
            'registration_id': str(registration.id)
        })
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid request.'}, status=400)
    except Exception as e:
        logger.error(f'Event registration verify error: {str(e)}')
        return JsonResponse({'status': 'error', 'message': 'An error occurred.'}, status=500)


@require_http_methods(["POST"])
def submit_event_feedback_ajax(request, pk):
    """AJAX endpoint for submitting event feedback (registered attendees only)."""
    try:
        event = get_object_or_404(Event, pk=pk, is_published=True)
        if not event.feedback_enabled:
            return JsonResponse({'status': 'error', 'message': 'Feedback is not open for this event.'}, status=403)
        data = json.loads(request.body)
        registration_id = data.get('registration_id', '').strip()
        rating = data.get('rating')
        comment = data.get('comment', '').strip()
        if not registration_id or not rating or not comment:
            return JsonResponse({'status': 'error', 'message': 'All fields are required.'}, status=400)
        # Validate rating
        try:
            rating = int(rating)
            if rating not in range(1, 6):
                raise ValueError
        except (ValueError, TypeError):
            return JsonResponse({'status': 'error', 'message': 'Invalid rating.'}, status=400)
        # Validate registration belongs to this event
        try:
            from uuid import UUID
            reg_uuid = UUID(registration_id)
        except (ValueError, AttributeError):
            return JsonResponse({'status': 'error', 'message': 'Invalid registration.'}, status=400)
        registration = get_object_or_404(EventRegistration, id=reg_uuid, event=event)
        # Prevent duplicate feedback
        if hasattr(registration, 'feedback'):
            return JsonResponse({'status': 'error', 'message': 'You have already submitted feedback for this event.'}, status=409)
        EventFeedback.objects.create(
            event=event,
            registration=registration,
            reviewer_name=registration.name,
            rating=rating,
            comment=comment
        )
        return JsonResponse({'status': 'success', 'message': 'Thank you for your feedback! It will appear after review.'})
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid request.'}, status=400)
    except Exception as e:
        logger.error(f'Event feedback error: {str(e)}')
        return JsonResponse({'status': 'error', 'message': 'An error occurred. Please try again.'}, status=500)


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
                'message': 'All fields are required.'
            }, status=400)

        # Validate rating range
        if rating not in [1, 2, 3, 4, 5]:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid rating value.'
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
            'message': 'Thank you! Your review has been submitted for approval.'
        })
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON.'}, status=400)
    except Exception as e:
        logger.error(f'Error in submit_review_ajax: {str(e)}')
        return JsonResponse({'status': 'error', 'message': 'An error occurred. Please try again.'}, status=500)


@require_http_methods(["POST"])
def book_appointment_ajax(request):
    """AJAX endpoint for booking appointments from public portal."""
    try:
        data = json.loads(request.body)
        patient_name = data.get('name', '').strip()
        patient_phone = data.get('phone', '').strip()
        patient_email = data.get('email', '').strip()
        practitioner_id = data.get('practitioner_id', '').strip()
        if practitioner_id:
            try:
                practitioner_id = decode_b64uuid(practitioner_id)
            except Exception:
                pass
        app_date = data.get('date', '').strip()
        app_time = data.get('time', '').strip()
        notes = data.get('notes', '').strip()

        # Validate required fields
        if not all([patient_name, patient_phone, app_date, app_time]):
            return JsonResponse({
                'status': 'error',
                'message': 'All fields are required including time.'
            }, status=400)

        # Try to find an existing patient by phone
        patient = Patient.objects.filter(phone=patient_phone).first()
        
        # Update email if patient exists and a new email was provided
        if patient and patient_email and patient.email != patient_email:
            patient.email = patient_email
            patient.save(update_fields=['email'])
        
        practitioner = None
        if practitioner_id:
            practitioner = Practitioner.objects.filter(id=practitioner_id, is_active=True).first()
        
        # Create appointment
        if patient:
            appointment = Appointment.objects.create(
                patient=patient,
                practitioner=practitioner,
                appointment_date=app_date,
                appointment_time=app_time,
                appointment_type='physical',
                status='scheduled',
                reason=notes
            )
        else:
            # Guest booking
            appointment = Appointment.objects.create(
                guest_name=patient_name,
                guest_phone=patient_phone,
                guest_email=patient_email,
                practitioner=practitioner,
                appointment_date=app_date,
                appointment_time=app_time,
                appointment_type='physical',
                status='scheduled',
                reason=notes
            )
        
        logger.info(f'New appointment booked by {patient_name} for {app_date}')

        # Send booking confirmation email to patient + notify admin
        try:
            from clinic.email_utils import send_booking_confirmation_email
            send_booking_confirmation_email(appointment, request)
        except Exception as email_err:
            logger.error(f'Booking email failed: {email_err}')

        return JsonResponse({
            'status': 'success',
            'message': 'Appointment booked successfully! A confirmation email has been sent.'
        })
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON.'}, status=400)
    except Exception as e:
        logger.error(f'Error in book_appointment_ajax: {str(e)}')
        return JsonResponse({'status': 'error', 'message': 'An error occurred. Please try again.'}, status=500)


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


@require_http_methods(["POST"])
def register_for_course_ajax(request, pk):
    """AJAX endpoint for course batch registration."""
    from courses.models import Course, CourseRegistration
    try:
        course = get_object_or_404(Course, pk=pk, is_published=True)
        active_batch = course.active_batch
        
        if not active_batch:
            return JsonResponse({'status': 'error', 'message': 'No active intake for this course currently.'}, status=400)
            
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        phone = data.get('phone', '').strip()
        email = data.get('email', '').strip()
        
        if not name or not phone:
            return JsonResponse({'status': 'error', 'message': 'Name and phone are required.'}, status=400)
            
        # Check if already registered for THIS batch
        if CourseRegistration.objects.filter(batch=active_batch, phone=phone).exists():
            return JsonResponse({'status': 'error', 'message': 'You are already registered for this intake.'}, status=409)
            
        CourseRegistration.objects.create(
            batch=active_batch,
            name=name,
            phone=phone,
            email=email
        )
        
        logger.info(f'New student {name} registered for course {course.title} (Batch: {active_batch.name})')
        return JsonResponse({'status': 'success', 'message': f'Successfully registered for {active_batch.name}! We will contact you shortly.'})
        
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid request.'}, status=400)
    except Exception as e:
        logger.error(f'Course registration error: {str(e)}')
        return JsonResponse({'status': 'error', 'message': 'An error occurred. Please try again.'}, status=500)


@require_http_methods(["POST"])
def verify_course_registration_ajax(request, pk):
    """Verify if a student was in a PAST batch to allow feedback."""
    from courses.models import Course, CourseRegistration
    try:
        course = get_object_or_404(Course, pk=pk, is_published=True)
        data = json.loads(request.body)
        identifier = data.get('identifier', '').strip()
        
        if not identifier:
            return JsonResponse({'status': 'error', 'message': 'Please enter your phone or email.'}, status=400)
            
        from django.db.models import Q
        # Search registrations for ALL batches of this course
        registration = CourseRegistration.objects.filter(
            batch__course=course,
            batch__feedback_enabled=True # Batch must have feedback enabled
        ).filter(
            Q(phone=identifier) | Q(email__iexact=identifier)
        ).first()
        
        if not registration:
            return JsonResponse({
                'status': 'not_found',
                'message': 'No past record found. Feedback is only allowed for previous students.'
            }, status=404)
            
        if hasattr(registration, 'feedback'):
            return JsonResponse({
                'status': 'already_submitted',
                'message': 'You have already shared your experience for this course.'
            }, status=409)
            
        return JsonResponse({
            'status': 'verified',
            'name': registration.name,
            'registration_id': str(registration.id)
        })
    except Exception as e:
        logger.error(f'Course feedback verify error: {str(e)}')
        return JsonResponse({'status': 'error', 'message': 'Verification service error.'}, status=500)


@require_http_methods(["POST"])
def submit_course_feedback_ajax(request, pk):
    """Submit feedback for a course (verified past students only)."""
    from courses.models import Course, CourseRegistration, CourseFeedback
    try:
        course = get_object_or_404(Course, pk=pk, is_published=True)
        data = json.loads(request.body)
        registration_id = data.get('registration_id')
        rating = data.get('rating')
        comment = data.get('comment', '').strip()
        
        if not all([registration_id, rating, comment]):
            return JsonResponse({'status': 'error', 'message': 'Complete all feedback fields.'}, status=400)
            
        registration = get_object_or_404(CourseRegistration, id=registration_id, batch__course=course)
        
        if hasattr(registration, 'feedback'):
            return JsonResponse({'status': 'error', 'message': 'Feedback already exists.'}, status=409)
            
        CourseFeedback.objects.create(
            course=course,
            batch=registration.batch,
            registration=registration,
            reviewer_name=registration.name,
            rating=int(rating),
            comment=comment
        )
        
        return JsonResponse({'status': 'success', 'message': 'Thank you! Your feedback helps other students choose better.'})
    except Exception as e:
        logger.error(f'Course feedback submission error: {str(e)}')
        return JsonResponse({'status': 'error', 'message': 'Submission failed.'}, status=500)


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
        if self.request.method == 'GET':
            return [IsAuthenticatedOrReadOnly()]
        return [IsAuthenticated, IsDoctor()]
    
    def get_queryset(self):
        # Non-authenticated users only see active practitioners
        if not self.request.user.is_authenticated:
            return Practitioner.objects.filter(is_active=True)
        return Practitioner.objects.all()

# ── Admin Global Search ───────────────────────────────────────────────────

from django.contrib.auth.decorators import login_required
from patients.models import Patient
from appointments.models import Appointment
from django.db.models import Q
from django.urls import reverse

@login_required
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
