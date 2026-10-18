"""Public event pages. Registrants act through a secret per-registration token, never through guessable ids."""
from django.utils.translation import gettext
import json
import logging

from django.contrib import messages
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone, translation
from django.views.decorators.http import require_http_methods, require_POST
from django_ratelimit.decorators import ratelimit

from spinalcure.utils import parse_uuid_param
from spinalcure.validators import validate_phone_number

from . import service
from .models import Event, EventFeedback, EventRegistration

logger = logging.getLogger(__name__)

PUBLIC_PHASES = ('upcoming', 'live', 'completed', 'cancelled')


def _public_events():
    return Event.objects.filter(status__in=('published', 'cancelled'))


def public_event_list(request):
    """Upcoming / live / completed / cancelled with search, filters and pagination."""
    phase = request.GET.get('phase', 'upcoming')
    if phase not in PUBLIC_PHASES:
        phase = 'upcoming'
    q, etype = request.GET.get('q', '').strip()[:100], request.GET.get('type', '')
    lang, online = request.GET.get('language', ''), request.GET.get('mode', '')
    qs = _public_events().order_by('date', 'start_time')
    if q:
        qs = qs.filter(title__icontains=q) | qs.filter(presenter__icontains=q) | qs.filter(description__icontains=q)
    if etype in dict(Event.EVENT_TYPE_CHOICES):
        qs = qs.filter(event_type=etype)
    if lang in ('en', 'ta', 'hi', 'ar'):
        qs = qs.filter(language=lang)
    if online in ('online', 'in_person'):
        qs = qs.filter(is_online=(online == 'online'))
    events = [e for e in qs.distinct() if e.phase == phase]
    if phase in ('completed', 'cancelled'):
        events.reverse()
    page = Paginator(events, 9).get_page(request.GET.get('page'))
    counts = {p: 0 for p in PUBLIC_PHASES}
    for e in _public_events():
        counts[e.phase] += 1
    return render(request, 'events/public_list.html', {
        'events': page, 'phase': phase, 'phases': PUBLIC_PHASES, 'counts': counts, 'q': q, 'etype': etype,
        'language': lang, 'mode': online, 'event_types': Event.EVENT_TYPE_CHOICES})


def public_event_detail(request, pk):
    event = get_object_or_404(_public_events(), pk=pk)
    feedbacks = event.feedbacks.filter(is_published=True)
    ratings = [f.rating for f in feedbacks]
    now = timezone.now()
    closed_reason = ''
    if event.status == 'cancelled':
        closed_reason = 'cancelled'
    elif event.phase == 'completed':
        closed_reason = 'ended'
    elif event.registration_deadline and now > event.registration_deadline:
        closed_reason = 'deadline'
    elif event.is_full and not event.waitlist_enabled:
        closed_reason = 'full'
    return render(request, 'clinic/event_detail.html', {
        'event': event, 'feedbacks': feedbacks, 'avg_rating': round(sum(ratings) / len(ratings), 1) if ratings else 0,
        'rating_range': range(1, 6), 'closed_reason': closed_reason, 'waitlist_only': event.is_full and event.waitlist_enabled,
        'start_iso': event.starts_at.isoformat(), 'ics_url': reverse('event_ics', args=[event.pk]),
        'og_url': request.build_absolute_uri()})


@require_http_methods(['POST'])
@ratelimit(key='ip', rate='20/h', method='POST', block=True)
def register_for_event(request, pk):
    def fail(msg, status=400, code='invalid'):
        return JsonResponse({'status': 'error', 'code': code, 'message': msg}, status=status)

    event = get_object_or_404(_public_events(), pk=pk)
    try:
        data = json.loads(request.body or b'{}')
        if not isinstance(data, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        return fail('Invalid request.')
    if str(data.get('website', '')).strip():                     # honeypot
        return JsonResponse({'status': 'success', 'outcome': 'confirmed', 'message': gettext('Registration received.')})
    name = str(data.get('name', '')).strip()[:200]
    phone = str(data.get('phone', '')).strip()[:20]
    email = str(data.get('email', '')).strip()[:254]
    notes = str(data.get('notes', '')).strip()[:1000]
    if len(name) < 2 or not phone:
        return fail('Name and phone are required.')
    try:
        validate_phone_number(phone)
        if email:
            validate_email(email)
    except ValidationError:
        return fail('Please check your phone number and email address.')
    try:
        reg = service.register(event, name=name, phone=phone, email=email, notes=notes,
                               language=translation.get_language() or 'en')
    except service.EventError as exc:
        return fail(exc.message, 409 if exc.code in ('duplicate', 'full') else 400, exc.code)
    return JsonResponse({
        'status': 'success', 'outcome': reg.status,
        'message': ('Registration confirmed!' if reg.status == 'confirmed'
                    else 'The event is full. You are on the waitlist and will be told if a place opens.'),
        'manage_url': request.build_absolute_uri(service.manage_path(reg)),
    })


def event_ics(request, pk):
    """Calendar entry for a published event. Never contains the private meeting link."""
    event = get_object_or_404(_public_events(), pk=pk)
    body = service.build_ics(event, base_url=request.build_absolute_uri(reverse('event_detail', args=[event.pk])))
    resp = HttpResponse(body, content_type='text/calendar; charset=utf-8')
    resp['Content-Disposition'] = f'attachment; filename="event-{event.pk}.ics"'
    return resp


def _reg(token):
    if not token or len(token) > 64:
        raise Http404
    return get_object_or_404(EventRegistration.objects.select_related('event'), access_token=token)


def registration_ics(request, token):
    reg = _reg(token)
    body = service.build_ics(reg.event, base_url=request.build_absolute_uri(service.manage_path(reg)))
    resp = HttpResponse(body, content_type='text/calendar; charset=utf-8')
    resp['Content-Disposition'] = f'attachment; filename="event-{reg.event_id}.ics"'
    return resp


@ratelimit(key='ip', rate='120/h', method=['GET', 'POST'], block=True)
def registration_manage(request, token):
    reg = _reg(token)
    event = reg.event
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'cancel':
                service.cancel_registration(reg)
                messages.success(request, gettext('Your registration has been cancelled.'))
            elif action == 'feedback':
                _save_feedback(reg, request.POST)
                messages.success(request, gettext('Thank you for your feedback.'))
            else:
                messages.error(request, gettext('Unknown action.'))
        except service.EventError as exc:
            messages.error(request, exc.message)
        return redirect('event_registration_manage', token=token)
    can_feedback = (reg.status == 'confirmed' and event.feedback_enabled and event.phase == 'completed'
                    and not hasattr(reg, 'feedback'))
    return render(request, 'events/registration_manage.html', {
        'reg': reg, 'event': event, 'join': service.join_info(reg), 'can_feedback': can_feedback,
        'can_cancel': reg.status != 'cancelled' and event.phase in ('upcoming',),
        'ics_url': reverse('registration_ics', args=[token]), 'rating_range': range(1, 6)})


def _save_feedback(reg, post):
    event = reg.event
    if reg.status != 'confirmed' or not event.feedback_enabled or event.phase != 'completed':
        raise service.EventError('closed', gettext('Feedback is not open for this event.'))
    if hasattr(reg, 'feedback'):
        raise service.EventError('duplicate', gettext('You have already sent feedback. Thank you!'))
    try:
        rating = int(post.get('rating', ''))
        if rating not in range(1, 6):
            raise ValueError
    except ValueError:
        raise service.EventError('invalid', gettext('Please choose a rating from 1 to 5.'))
    EventFeedback.objects.create(event=event, registration=reg, reviewer_name=reg.name, rating=rating,
                                 comment=post.get('comment', '').strip()[:1000], is_published=False)
