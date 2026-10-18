from django.utils import timezone
from django.http import HttpResponse
from django.shortcuts import redirect
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from spinalcure.decorators import role_required
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
from urllib.parse import quote
from django.core.exceptions import ValidationError
from django.db import transaction
from appointments.scheduling import booking_lock, check_bookable, parse_day_time, BookingError
from spinalcure.validators import validate_phone_number
from spinalcure.permissions import ReadWritePerm
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
    events = Event.objects.filter(is_published=True, is_cancelled=False, is_archived=False, date__gte=timezone.localdate()).order_by('date', 'start_time')

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
    """Public event registration: capacity, waitlist, deadline and duplicates enforced server-side."""
    from events.registration import register, RegistrationError
    from spinalcure.utils import rate_limited, client_ip
    if rate_limited(f'event_register:{client_ip(request)}', 10, 3600):
        return JsonResponse({'status': 'error', 'message': 'Too many attempts. Please try again later.'}, status=429)
    event = get_object_or_404(Event, pk=pk, is_published=True)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid request.'}, status=400)
    name, phone = str(data.get('name', '')).strip()[:200], str(data.get('phone', '')).strip()
    email, notes = str(data.get('email', '')).strip(), str(data.get('notes', '')).strip()[:1000]
    if not name or not phone:
        return JsonResponse({'status': 'error', 'message': 'Name and phone are required.'}, status=400)
    try:
        validate_phone_number(phone)
        if email:
            from django.core.validators import validate_email
            validate_email(email)
    except ValidationError:
        return JsonResponse({'status': 'error', 'message': 'Please enter a valid phone number and email.'}, status=400)
    try:
        reg = register(request, event.pk, name, phone, email, notes)
    except RegistrationError as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=409)
    msg = ('You are registered! ' if reg.status == 'confirmed' else 'The event is full, so you are on the waitlist. ')
    msg += 'A confirmation email with your registration link has been sent.' if email else 'Please save your registration link.'
    return JsonResponse({'status': 'success', 'registration_status': reg.status, 'message': msg,
                         'manage_url': reverse('event_registration_manage', args=[reg.access_token])})


def event_registration_manage_view(request, token):
    """Registrant's private page: status, cancel, calendar file and (when live) the meeting link."""
    from events.models import EventRegistration
    from events.registration import cancel
    reg = get_object_or_404(EventRegistration.objects.select_related('event'), access_token=token)
    if request.method == 'POST' and request.POST.get('action') == 'cancel':
        cancel(request, reg)
        messages.success(request, 'Your registration has been cancelled.')
        return redirect('event_registration_manage', token=token)
    from django.utils import timezone
    from datetime import timedelta
    e = reg.event
    can_join = (e.is_online and e.meeting_link and reg.status == 'confirmed' and not e.is_cancelled
                and e.starts_at - timedelta(minutes=30) <= timezone.now() <= e.ends_at)
    resp = render(request, 'clinic/event_registration.html', {'reg': reg, 'event': e, 'can_join': can_join,
                                                               'clinic': ClinicProfile.objects.first()})
    resp['X-Robots-Tag'] = 'noindex'
    resp['Referrer-Policy'] = 'no-referrer'
    return resp


def event_join_view(request, token):
    """Redirect confirmed registrants to the private meeting link, only from 30 minutes before start until the end."""
    from events.models import EventRegistration
    from django.utils import timezone
    from datetime import timedelta
    reg = get_object_or_404(EventRegistration.objects.select_related('event'), access_token=token)
    e = reg.event
    if not (e.is_online and e.meeting_link and reg.status == 'confirmed' and not e.is_cancelled):
        messages.error(request, 'The meeting link is only available to confirmed registrants of active online events.')
    elif not (e.starts_at - timedelta(minutes=30) <= timezone.now() <= e.ends_at):
        messages.info(request, 'The meeting link opens 30 minutes before the start time.')
    else:
        if reg.attended is None:
            reg.attended = True
            reg.save(update_fields=['attended'])
        return redirect(e.meeting_link)
    return redirect('event_registration_manage', token=token)


def event_ics_view(request, pk):
    from events.registration import ics
    event = get_object_or_404(Event, pk=pk, is_published=True)
    resp = HttpResponse(ics(event, request.build_absolute_uri(reverse('event_detail', args=[pk]))), content_type='text/calendar; charset=utf-8')
    resp['Content-Disposition'] = 'attachment; filename="event.ics"'
    return resp


def public_event_list_view(request):
    """Public listing with upcoming / live / completed / cancelled tabs, search and pagination."""
    from django.core.paginator import Paginator
    from django.utils import timezone
    tab = request.GET.get('tab', 'upcoming')
    q = request.GET.get('q', '').strip()
    events = Event.objects.filter(is_published=True, is_archived=False)
    if q:
        events = events.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(presenter__icontains=q))
    if request.GET.get('type'):
        events = events.filter(event_type=request.GET['type'])
    today = timezone.localdate()
    if tab == 'cancelled':
        events = events.filter(is_cancelled=True).order_by('-date')
    else:
        events = events.filter(is_cancelled=False)
        if tab == 'completed':
            events = events.filter(date__lte=today).order_by('-date', '-start_time')
        else:
            events = events.filter(date__gte=today).order_by('date', 'start_time')
        events = [e for e in events if e.phase == tab] if tab in ('live', 'completed', 'upcoming') else events
    page = Paginator(events, 12).get_page(request.GET.get('page'))
    return render(request, 'clinic/event_list.html', {'page': page, 'tab': tab, 'q': q,
                                                      'types': Event._meta.get_field('event_type').choices,
                                                      'clinic': ClinicProfile.objects.first()})


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
        patient = Patient.by_phone(patient_phone) or Patient.objects.create(
            phone=patient_phone, name=patient_name, chief_complaint='Review submission'
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
    from spinalcure.utils import rate_limited, client_ip
    if rate_limited(f'public_booking:{client_ip(request)}', 10, 3600):
        return JsonResponse({'status': 'error', 'message': 'Too many booking attempts. Please call the clinic.'}, status=429)
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

        if len(patient_name) > 255 or len(notes) > 300:
            return JsonResponse({'status': 'error', 'message': 'Name or notes are too long.'}, status=400)
        try:
            validate_phone_number(patient_phone)
            day, start = parse_day_time(app_date, app_time)
        except (ValidationError, BookingError):
            return JsonResponse({'status': 'error', 'message': 'Please enter a valid phone number, date and time.'}, status=400)

        # Never update an existing patient's record from this unauthenticated form: changing the
        # email here would redirect that patient's portal login codes to whoever typed it.
        patient = Patient.by_phone(patient_phone)

        practitioner = None
        if practitioner_id:
            practitioner = Practitioner.objects.filter(id=practitioner_id, is_active=True).first()
            if practitioner is None:
                return JsonResponse({'status': 'error', 'message': 'Please choose a valid practitioner.'}, status=400)

        appointment_type = 'online' if data.get('type') == 'online' else 'physical'
        fields = dict(practitioner=practitioner, appointment_date=day, appointment_time=start,
                      appointment_type=appointment_type, status='scheduled', reason=notes)
        if patient:
            fields['patient'] = patient
        else:
            fields.update(guest_name=patient_name, guest_phone=patient_phone, guest_email=patient_email or None)
        try:
            with booking_lock(practitioner.pk if practitioner else None, day), transaction.atomic():
                error = check_bookable(practitioner, day, start, 30, appointment_type)
                if error:
                    return JsonResponse({'status': 'error', 'message': error}, status=409)
                appointment = Appointment.objects.create(**fields)
        except BookingError as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=409)

        logger.info('Public appointment %s booked for %s', appointment.pk, day)
        from appointments.notify import appointment_changed
        appointment_changed(appointment, 'booked', public=True)

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
            
        from django.db import transaction
        from courses.models import CourseBatch
        with transaction.atomic():
            batch = CourseBatch.objects.select_for_update().get(pk=active_batch.pk)  # serialise seat checks
            if CourseRegistration.objects.filter(batch=batch, phone=phone).exclude(status='cancelled').exists():
                return JsonResponse({'status': 'error', 'message': 'You are already registered for this intake.'}, status=409)
            taken = CourseRegistration.objects.filter(batch=batch, status='confirmed').count()
            status = 'waitlisted' if batch.max_participants and taken >= batch.max_participants else 'confirmed'
            CourseRegistration.objects.create(batch=batch, name=name[:200], phone=phone, email=email, status=status)
        if email:
            from notifications.services import queue_email
            queue_email(email, 'event_registration', f'{course.title}: registration {"received" if status == "confirmed" else "waitlisted"}',
                        f'Thank you, {name}. You are {"registered" if status == "confirmed" else "on the waitlist"} for '
                        f'{course.title} ({batch.name}, starting {batch.start_date:%d %b %Y}). We will contact you with details.')
        if status == 'waitlisted':
            return JsonResponse({'status': 'success', 'registration_status': status,
                                 'message': f'{batch.name} is full, so you are on the waitlist. We will contact you if a seat opens.'})
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
    permission_classes = [ReadWritePerm(None, 'site_manage')]
    filterset_fields = ['is_active', 'gender']
    search_fields = ['name', 'specialization', 'designation_tag', 'qualifications']
    
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

@role_required('patients_view')
def global_search_ajax(request):
    """Fast AJAX search for top nav bar (Admin only)"""
    query = request.GET.get('q', '').strip()
    if not query or len(query) < 2:
        return JsonResponse({'results': []})

    results = []

    # Search Patients
    patients = Patient.search(Patient.objects.all(), query)[:5]
    detail_ok = request.user.can('clinical_view')
    for p in patients:
        results.append({
            'type': 'Patient',
            'title': p.name,
            'subtitle': p.phone,
            'url': reverse('patient-detail', args=[p.id]) if detail_ok else reverse('patient-list') + '?q=' + quote(p.patient_id_str or p.name),
            'icon': 'bi-person'
        })

    # Search Appointments
    appointments = Appointment.objects.filter(
        Q(patient__in=Patient.search(Patient.objects.all(), query)) |
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
