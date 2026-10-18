from django.utils.translation import gettext
from datetime import datetime
import logging

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from rest_framework import viewsets
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated

from spinalcure.decorators import require_pin_auth
from spinalcure.rbac import has_capability, require_capability
from spinalcure.utils import SpinalCureExport, log_action, parse_uuid_param

from . import service
from .forms import EventForm
from .models import Event, EventFeedback, EventRegistration
from .serializers import EventPublicSerializer, EventSerializer

logger = logging.getLogger(__name__)

PHASES = ('upcoming', 'live', 'completed', 'cancelled', 'draft', 'archived')


class EventViewSet(viewsets.ModelViewSet):
    """
    Anonymous and non-managers: read-only, published events, public fields only (no meeting details).
    Managers (events.manage): full CRUD; status changes go through the lifecycle endpoints, not PATCH.
    """
    filterset_fields = ['event_type', 'is_online', 'status', 'language']

    def get_permissions(self):
        class _Perm(BasePermission):
            def has_permission(self, request, view):
                if request.method in SAFE_METHODS:
                    return True
                return has_capability(request.user, 'events.manage')
        return [_Perm()]

    def _manager(self):
        return has_capability(self.request.user, 'events.manage')

    def get_serializer_class(self):
        return EventSerializer if self._manager() else EventPublicSerializer

    def get_queryset(self):
        qs = Event.objects.select_related('organizer', 'clinic').order_by('date', 'start_time')
        return qs if self._manager() else qs.filter(status='published')

    def get_object(self):
        # The serializer emits base64 ids; accept those as well as canonical UUIDs in the URL.
        key = self.lookup_url_kwarg or self.lookup_field
        parsed = parse_uuid_param(self.kwargs.get(key))
        if parsed is None:
            from django.http import Http404
            raise Http404
        self.kwargs[key] = str(parsed)
        return super().get_object()

    def perform_create(self, serializer):
        serializer.save(organizer=self.request.user)


def _need(request, capability):
    if has_capability(request.user, capability):
        return None
    messages.error(request, gettext('You do not have permission to perform this action.'))
    return redirect('dashboard')


def _filtered(request):
    query = request.GET.get('q', '').strip()
    phase = request.GET.get('phase', '')
    etype = request.GET.get('type', '')
    qs = Event.objects.annotate(
        n_confirmed=Count('registrations', filter=Q(registrations__status='confirmed')),
        n_waitlisted=Count('registrations', filter=Q(registrations__status='waitlisted'))
    ).order_by('-date', '-start_time')
    if query:
        qs = qs.filter(Q(title__icontains=query) | Q(description__icontains=query) | Q(presenter__icontains=query))
    if etype:
        qs = qs.filter(event_type=etype)
    if phase in ('draft', 'archived'):
        qs = qs.filter(status=phase)
    elif phase in ('upcoming', 'live', 'completed', 'cancelled'):
        qs = [e for e in qs if e.status != 'draft' and e.status != 'archived' and e.phase == phase]
    return qs, query, phase, etype


@require_capability('events.manage')
def event_list_view(request):
    """Staff list with phase tabs, search, type filter and pagination."""
    qs, query, phase, etype = _filtered(request)
    page = Paginator(qs, 9).get_page(request.GET.get('page'))
    params = {k: v for k, v in (('q', query), ('phase', phase), ('type', etype)) if v}
    from urllib.parse import urlencode
    export = ('?' + urlencode(params)) if params else ''
    context = {
        'events': page, 'search_query': query, 'phase': phase, 'phases': PHASES, 'etype': etype,
        'event_types': Event.EVENT_TYPE_CHOICES, 'filter_qs': urlencode(params),
        'export_events_excel_url': reverse('export_events_excel') + export,
        'export_events_csv_url': reverse('export_events_csv') + export,
        'export_events_pdf_url': reverse('export_events_pdf') + export,
        'export_events_copy_url': reverse('export_events_copy') + export,
        'export_events_print_url': reverse('export_events_print') + export,
    }
    if request.headers.get('HX-Request'):
        return render(request, 'events/partials/event_list_partial.html', context)
    return render(request, 'events/event_list.html', context)


@require_capability('events.manage')
def event_create_view(request):
    form = EventForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        event = form.save(commit=False)
        event.organizer, event.status = request.user, 'draft'
        from clinic.models import ClinicProfile
        event.clinic = ClinicProfile.objects.first()
        event.save()
        log_action(request, 'create', 'Event', event.title, object_id=event.id)
        messages.success(request, gettext('Event "%(title)s" saved as a draft. Publish it when you are ready.') % {'title': event.title})
        return redirect('event_registrations', pk=event.pk)
    return render(request, 'events/event_form.html', {'form': form, 'is_edit': False})


@require_capability('events.manage')
@require_pin_auth('event_list')
def event_edit_view(request, pk):
    event = get_object_or_404(Event, pk=pk)
    before = service.schedule_signature(event)
    form = EventForm(request.POST or None, request.FILES or None, instance=event)
    if request.method == 'POST' and form.is_valid():
        event = form.save()
        informed = service.announce_changes(event, before)
        if event.status == 'published':
            service.promote_waitlist(event)     # capacity may have grown
        log_action(request, 'update', 'Event', event.title, object_id=pk)
        messages.success(request, f'Event "{event.title}" updated.' + (
            f' {informed} registrant(s) were notified of the change.' if informed else ''))
        return redirect('event_list')
    return render(request, 'events/event_form.html', {'form': form, 'event': event, 'is_edit': True})


@require_POST
@require_capability('events.manage')
def event_status(request, pk):
    """Publish / unpublish / cancel / archive."""
    event = get_object_or_404(Event, pk=pk)
    action = request.POST.get('action')
    try:
        if action == 'publish':
            service.publish(event)
            messages.success(request, gettext('"%(title)s" is now published.') % {'title': event.title})
        elif action == 'unpublish':
            service.unpublish(event)
            messages.success(request, gettext('"%(title)s" is now a draft and hidden from the public site.') % {'title': event.title})
        elif action == 'cancel':
            service.cancel_event(event, request.POST.get('reason', ''))
            messages.success(request, gettext('"%(title)s" was cancelled and registrants were notified.') % {'title': event.title})
        elif action == 'archive':
            service.archive(event)
            messages.success(request, gettext('"%(title)s" was archived.') % {'title': event.title})
        else:
            messages.error(request, gettext('Unknown action.'))
            return redirect('event_list')
    except service.EventError as exc:
        messages.error(request, exc.message)
    except Exception as exc:     # ValidationError from full_clean on publish
        from django.core.exceptions import ValidationError
        if isinstance(exc, ValidationError):
            messages.error(request, 'Cannot publish: ' + '; '.join(exc.messages))
        else:
            raise
    else:
        log_action(request, 'update', 'Event', event.title, object_id=pk, changes={'status': {'new': event.status}})
    return redirect(request.POST.get('next') or 'event_list')


@require_POST
@require_capability('events.manage')
def toggle_event_publish(request, pk):
    """Kept for existing links: flips between published and draft."""
    event = get_object_or_404(Event, pk=pk)
    request.POST = request.POST.copy()
    request.POST['action'] = 'unpublish' if event.status == 'published' else 'publish'
    return event_status(request, pk)


@require_capability('events.manage')
@require_pin_auth('event_list')
def event_delete_view(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if request.method == 'POST':
        if event.registrations.exclude(status='cancelled').exists() and event.status != 'cancelled':
            msg = 'This event has registrations. Cancel it (which notifies them) before deleting.'
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': msg}, status=409)
            messages.error(request, msg)
            return redirect('event_list')
        title, event_id = event.title, event.id
        event.delete()
        log_action(request, 'delete', 'Event', title, object_id=event_id)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
            return JsonResponse({'status': 'ok', 'redirect_url': reverse('event_list')})
        messages.success(request, gettext('Event "%(title)s" deleted.') % {'title': title})
    return redirect('event_list')


@require_capability('events.registrations')
def event_registrations_view(request, pk):
    """Attendee list: search, status filter, attendance, cancel/promote."""
    event = get_object_or_404(Event, pk=pk)
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    regs = event.registrations.all()
    if query:
        from .service import phone_key
        match = Q(name__icontains=query) | Q(email__icontains=query) | Q(phone__icontains=query)
        digits = phone_key(query)
        if len(digits) >= 3:               # an empty/short key would match every row
            match |= Q(phone_key__icontains=digits)
        regs = regs.filter(match)
    if status in ('confirmed', 'waitlisted', 'cancelled'):
        regs = regs.filter(status=status)
    regs = regs.order_by('status', 'registered_at')
    page = Paginator(regs, 20).get_page(request.GET.get('page'))
    counts = {s: event.registrations.filter(status=s).count() for s in ('confirmed', 'waitlisted', 'cancelled')}
    context = {
        'event': event, 'registrations': page, 'search_query': query, 'status': status, 'counts': counts,
        'attended': event.registrations.filter(attended=True).count(),
        'export_event_registrations_excel_url': reverse('export_event_registrations_excel', kwargs={'pk': pk}),
        'export_event_registrations_csv_url': reverse('export_event_registrations_csv', kwargs={'pk': pk}),
        'export_event_registrations_pdf_url': reverse('export_event_registrations_pdf', kwargs={'pk': pk}),
        'export_event_registrations_copy_url': reverse('export_event_registrations_copy', kwargs={'pk': pk}),
        'export_event_registrations_print_url': reverse('export_event_registrations_print', kwargs={'pk': pk}),
        'can_manage': has_capability(request.user, 'events.manage'),
    }
    if request.headers.get('HX-Request'):
        return render(request, 'events/partials/event_registrations_partial.html', context)
    return render(request, 'events/event_registrations.html', context)


@require_POST
@require_capability('events.registrations')
def registration_action(request, pk, reg_pk):
    event = get_object_or_404(Event, pk=pk)
    reg = get_object_or_404(EventRegistration, pk=reg_pk, event=event)
    action = request.POST.get('action')
    try:
        if action in ('attended', 'not_attended'):
            service.mark_attended(reg, action == 'attended')
        elif action == 'cancel':
            service.cancel_registration(reg, by_staff=True)
            messages.success(request, gettext("Cancelled %(name)s's registration.") % {'name': reg.name})
        elif action == 'promote' and reg.status == 'waitlisted':
            if event.is_full:
                raise service.EventError('full', gettext('No seat is free. Raise the capacity or cancel a registration first.'))
            reg.status, reg.promoted_at = 'confirmed', timezone.now()
            reg.save(update_fields=['status', 'promoted_at'])
            service._notify_reg('event_promoted', reg)
            messages.success(request, gettext('%(name)s was moved from the waitlist.') % {'name': reg.name})
        else:
            messages.error(request, gettext('That action is not available for this registration.'))
    except service.EventError as exc:
        messages.error(request, exc.message)
    log_action(request, 'update', 'EventRegistration', f'{reg.name} / {event.title}', object_id=reg.pk,
               changes={'action': {'new': action}})
    return redirect(request.POST.get('next') or reverse('event_registrations', kwargs={'pk': pk}))


@require_capability('events.manage')
def event_feedback_admin_view(request, pk):
    event = get_object_or_404(Event, pk=pk)
    return render(request, 'events/event_feedback_admin.html', {
        'event': event, 'feedbacks': event.feedbacks.all().order_by('-submitted_at')})


@require_POST
@require_capability('events.manage')
def toggle_event_feedback(request, pk):
    event = get_object_or_404(Event, pk=pk)
    event.feedback_enabled = not event.feedback_enabled
    event.save(update_fields=['feedback_enabled'])
    messages.success(request, gettext('Feedback form %(value1)s for "%(title)s".') % {'value1': "enabled" if event.feedback_enabled else "disabled", 'title': event.title})
    return redirect('event_feedback_admin', pk=pk)


@require_POST
@require_capability('events.manage')
def toggle_feedback_publish(request, feedback_pk):
    feedback = get_object_or_404(EventFeedback, pk=feedback_pk)
    feedback.is_published = not feedback.is_published
    feedback.save(update_fields=['is_published'])
    messages.success(request, gettext('Feedback by %(reviewer_name)s %(value3)s.') % {'reviewer_name': feedback.reviewer_name, 'value3': "published" if feedback.is_published else "unpublished"})
    return redirect('event_feedback_admin', pk=feedback.event_id)


# ── Export logic ──

def _get_filtered_events(request):
    qs, query, _phase, _type = _filtered(request)
    return qs, query

def _event_mapping(e):
    return [e.title, e.get_event_type_display(), e.date.strftime('%Y-%m-%d'), e.venue or 'Online',
            f"{e.registrations.filter(status='confirmed').count()}/{e.max_participants or '∞'}", float(e.fees)]

@require_capability('events.registrations')
def export_events_excel(request):
    events, _ = _get_filtered_events(request)
    headers = ["Title", "Type", "Date", "Venue", "Participants", "Fees"]
    return SpinalCureExport.to_excel(events, headers, _event_mapping, "Events", "events")

@require_capability('events.registrations')
def export_events_csv(request):
    events, _ = _get_filtered_events(request)
    headers = ["Title", "Type", "Date", "Venue", "Participants", "Fees"]
    return SpinalCureExport.to_csv(events, headers, _event_mapping, "events")

@require_capability('events.registrations')
def export_events_pdf(request):
    events, query = _get_filtered_events(request)
    headers = ["Title", "Type", "Date", "Venue", "Participants", "Fees"]
    def pdf_mapping(e):
        return [e.title, e.get_event_type_display(), e.date.strftime('%b %d, %Y'), e.venue, f"{e.registrations.filter(status='confirmed').count()}/{e.max_participants or '∞'}", f"₹{e.fees:,.2f}"]
    title = f"Events Schedule {'(Filtered)' if query else ''}"
    return SpinalCureExport.to_pdf(events, headers, pdf_mapping, title, "events")

@require_capability('events.registrations')
def export_events_copy(request):
    events, _ = _get_filtered_events(request)
    headers = ["Title", "Type", "Date", "Venue", "Participants", "Fees"]
    text = SpinalCureExport.to_text(events, headers, _event_mapping)
    from django.http import HttpResponse
    return HttpResponse(text, content_type='text/plain')

@require_capability('events.registrations')
def export_events_print(request):
    events, query = _get_filtered_events(request)
    headers = ["Title", "Type", "Date", "Venue", "Participants", "Fees"]
    rows = [_event_mapping(e) for e in events]
    context = {
        'rows': rows,
        'title': 'Events Report',
        'query': query,
        'headers': headers,
        'now': datetime.now(),
    }
    return render(request, 'exports/print_template.html', context)

# ── Event Registration Export ──

def _registration_mapping(r):
    return [r.name, r.email, r.phone, r.get_status_display(), 'Yes' if r.attended else '',
            timezone.localtime(r.registered_at).strftime('%Y-%m-%d %H:%M')]

@require_capability('events.registrations')
def export_event_registrations_excel(request, pk):
    event = get_object_or_404(Event, pk=pk)
    registrations = event.registrations.all().order_by('-registered_at')
    headers = ["Name", "Email", "Phone", "Status", "Attended", "Registered"]
    return SpinalCureExport.to_excel(registrations, headers, _registration_mapping, f"Reg - {event.title[:20]}", "event_registrations")

@require_capability('events.registrations')
def export_event_registrations_csv(request, pk):
    event = get_object_or_404(Event, pk=pk)
    registrations = event.registrations.all().order_by('-registered_at')
    headers = ["Name", "Email", "Phone", "Status", "Attended", "Registered"]
    return SpinalCureExport.to_csv(registrations, headers, _registration_mapping, "event_registrations")

@require_capability('events.registrations')
def export_event_registrations_pdf(request, pk):
    event = get_object_or_404(Event, pk=pk)
    registrations = event.registrations.all().order_by('-registered_at')
    headers = ["Name", "Email", "Phone", "Status", "Attended", "Registered"]
    title = f"Registrations: {event.title}"
    return SpinalCureExport.to_pdf(registrations, headers, _registration_mapping, title, "event_registrations")

@require_capability('events.registrations')
def export_event_registrations_copy(request, pk):
    event = get_object_or_404(Event, pk=pk)
    registrations = event.registrations.all().order_by('-registered_at')
    headers = ["Name", "Email", "Phone", "Status", "Attended", "Registered"]
    text = SpinalCureExport.to_text(registrations, headers, _registration_mapping)
    from django.http import HttpResponse
    return HttpResponse(text, content_type='text/plain')

@require_capability('events.registrations')
def export_event_registrations_print(request, pk):
    event = get_object_or_404(Event, pk=pk)
    registrations = event.registrations.all().order_by('-registered_at')
    headers = ["Name", "Email", "Phone", "Status", "Attended", "Registered"]
    rows = [_registration_mapping(r) for r in registrations]
    context = {
        'rows': rows,
        'title': f'Registrations: {event.title}',
        'headers': headers,
        'now': datetime.now(),
    }
    return render(request, 'exports/print_template.html', context)
