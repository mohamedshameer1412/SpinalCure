from django.utils.translation import gettext
import json
import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from events.service import EventError
from spinalcure.validators import validate_phone_number

from . import service
from .forms import StudentProfileForm
from .models import Course, CourseFeedback, CourseRegistration

logger = logging.getLogger(__name__)


@require_http_methods(['POST'])
@ratelimit(key='ip', rate='20/h', method='POST', block=True)
def register_for_course(request, pk):
    def fail(msg, status=400, code='invalid'):
        return JsonResponse({'status': 'error', 'code': code, 'message': msg}, status=status)

    course = get_object_or_404(Course, pk=pk, is_published=True)
    batch = course.active_batch
    if not batch:
        return fail('No active intake for this course currently.', 400, 'closed')
    try:
        data = json.loads(request.body or b'{}')
        if not isinstance(data, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        return fail('Invalid request.')
    name, phone = str(data.get('name', '')).strip()[:200], str(data.get('phone', '')).strip()[:20]
    email, notes = str(data.get('email', '')).strip()[:254], str(data.get('notes', '')).strip()[:1000]
    if len(name) < 2 or not phone:
        return fail('Name and phone are required.')
    if course.fees > 0 and data.get('accept_terms') is not True:
        return fail(gettext('Please accept the terms and conditions.'), 400, 'terms')
    try:
        validate_phone_number(phone)
        if email:
            validate_email(email)
    except ValidationError:
        return fail('Please check your phone number and email address.')
    try:
        reg = service.register(batch, name=name, phone=phone, email=email, notes=notes)
    except EventError as exc:
        return fail(exc.message, 409 if exc.code == 'duplicate' else 400, exc.code)
    return JsonResponse({
        'status': 'success', 'outcome': reg.status,
        'message': (f'Successfully registered for {batch.name}!' if reg.status == 'confirmed'
                    else f'{batch.name} is full. You are on the waitlist and will be told if a place opens.'),
        'manage_url': request.build_absolute_uri(service.manage_path(reg)),
    })


@ratelimit(key='ip', rate='120/h', method=['GET', 'POST'], block=True)
def registration_manage(request, token):
    if not token or len(token) > 64:
        raise Http404
    reg = get_object_or_404(CourseRegistration.objects.select_related('batch__course'), access_token=token)
    batch = reg.batch
    student = reg.student if reg.student_id else service.link_student(reg)
    profile_form = None
    if reg.status == 'confirmed':
        profile_form = StudentProfileForm(request.POST if request.POST.get('action') == 'profile' else None,
                                          request.FILES if request.POST.get('action') == 'profile' else None, instance=student)
        if request.method == 'POST' and request.POST.get('action') == 'profile':
            if profile_form.is_valid():
                was_complete = student.profile_complete
                profile_form.save()
                reg.refresh_from_db()
                if not was_complete:
                    service.complete_profile(reg)
                messages.success(request, gettext('Thank you! Your details are saved.') if was_complete
                                 else gettext('Thank you! Your student ID card is ready below.'))
                return redirect('course_registration_manage', token=token)
    if request.method == 'POST' and request.POST.get('action') != 'profile':
        action = request.POST.get('action')
        try:
            if action == 'cancel':
                service.cancel_registration(reg)
                messages.success(request, gettext('Your registration has been cancelled.'))
            elif action == 'feedback':
                if reg.status != 'confirmed' or not batch.feedback_enabled or not batch.is_completed:
                    raise EventError('closed', gettext('Feedback is not open for this batch.'))
                if hasattr(reg, 'feedback'):
                    raise EventError('duplicate', gettext('You have already sent feedback. Thank you!'))
                try:
                    rating = int(request.POST.get('rating', ''))
                    if rating not in range(1, 6):
                        raise ValueError
                except ValueError:
                    raise EventError('invalid', gettext('Please choose a rating from 1 to 5.'))
                CourseFeedback.objects.create(course=batch.course, batch=batch, registration=reg,
                                              reviewer_name=reg.name, rating=rating,
                                              comment=request.POST.get('comment', '').strip()[:1000], is_published=False)
                messages.success(request, gettext('Thank you for your feedback.'))
            else:
                messages.error(request, gettext('Unknown action.'))
        except EventError as exc:
            messages.error(request, exc.message)
        return redirect('course_registration_manage', token=token)
    from django.utils import timezone
    return render(request, 'courses/registration_manage.html', {
        'reg': reg, 'batch': batch, 'course': batch.course, 'rating_range': range(1, 6),
        'student': student, 'profile_form': profile_form, 'card_ready': student.profile_complete and reg.status == 'confirmed',
        'can_cancel': reg.status != 'cancelled' and batch.start_date > timezone.localdate(),
        'can_feedback': (reg.status == 'confirmed' and batch.feedback_enabled and batch.is_completed
                         and not hasattr(reg, 'feedback'))})
