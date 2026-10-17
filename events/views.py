from django.contrib.auth.decorators import login_required
from spinalcure.decorators import role_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q
from spinalcure.utils import SpinalCureExport, log_action
from datetime import datetime
from django.views.decorators.http import require_http_methods
from .models import Event, EventRegistration, EventFeedback
from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated
from .serializers import EventSerializer
from spinalcure.permissions import IsDoctor
import logging
from spinalcure.permissions import ReadWritePerm
from spinalcure.decorators import require_pin_auth

logger = logging.getLogger(__name__)


class EventViewSet(viewsets.ModelViewSet):
    """
    ViewSet for event management.
    Everyone can view published events.
    Only doctors/admins can create/modify events.
    """
    queryset = Event.objects.all().order_by('date', 'start_time')
    serializer_class = EventSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['event_type', 'is_published', 'is_online']
    search_fields = ['title', 'description', 'venue']
    
    permission_classes = [ReadWritePerm(None, 'events_manage')]
    
    def get_queryset(self):
        user = self.request.user
        base_qs = Event.objects.select_related('organizer', 'clinic')
        if not user.is_authenticated:
            return base_qs.filter(is_published=True).order_by('date', 'start_time')
        return base_qs.all().order_by('date', 'start_time')


@role_required('events_manage')
def event_list_view(request):
    """List events - admin panel view."""
    
    query = request.GET.get('q', '')
    events = Event.objects.all().order_by('-date', '-start_time')
    
    if query:
        events = events.filter(Q(title__icontains=query) | Q(description__icontains=query))
    
    # Pagination
    paginator = Paginator(events, 9)  # Show 9 events per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Export URLs
    base_export_params = f"?q={query}" if query else ""
    from django.urls import reverse
    
    context = {
        'events': page_obj, 
        'search_query': query,
        'export_events_excel_url': reverse('export_events_excel') + base_export_params,
        'export_events_csv_url': reverse('export_events_csv') + base_export_params,
        'export_events_pdf_url': reverse('export_events_pdf') + base_export_params,
        'export_events_copy_url': reverse('export_events_copy') + base_export_params,
        'export_events_print_url': reverse('export_events_print') + base_export_params,
    }
    
    if request.headers.get('HX-Request'):
        return render(request, 'events/partials/event_list_partial.html', context)
        
    return render(request, 'events/event_list.html', context)

@role_required('events_manage')
def event_create_view(request):
    """Create a new event."""
    
    if request.method == 'POST':
        try:
            title = request.POST.get('title')
            event_type = request.POST.get('event_type')
            description = request.POST.get('description', '')
            date = request.POST.get('date')
            start_time = request.POST.get('start_time')
            end_time = request.POST.get('end_time')
            venue = request.POST.get('venue')
            max_participants = request.POST.get('max_participants')
            fees = request.POST.get('fees', 0)
            is_published = request.POST.get('is_published') == 'on'
            image = request.FILES.get('image')

            from clinic.models import ClinicProfile
            clinic = ClinicProfile.objects.first()

            event = Event.objects.create(
                title=title,
                event_type=event_type,
                description=description,
                date=date,
                start_time=start_time,
                end_time=end_time,
                venue=venue,
                max_participants=max_participants,
                fees=fees,
                is_published=is_published,
                image=image,
                organizer=request.user,
                clinic=clinic
            )
            log_action(request, 'create', 'Event', title, object_id=event.id)
            messages.success(request, f'Event "{title}" created successfully.')
            return redirect('event_list')
        except Exception as e:
            messages.error(request, f'Error creating event: {str(e)}')

    context = {
        'event_types': Event.EVENT_TYPE_CHOICES,
        'current_date': None, # Can pass current date if needed
    }
    return render(request, 'events/event_form.html', context)


@role_required('events_manage')
@require_pin_auth('event_list')
def event_edit_view(request, pk):
    """Edit an existing event."""
    
    event = get_object_or_404(Event, pk=pk)
    
    if request.method == 'POST':
        try:
            event.title = request.POST.get('title')
            event.event_type = request.POST.get('event_type')
            event.description = request.POST.get('description', '')
            event.date = request.POST.get('date')
            event.start_time = request.POST.get('start_time')
            event.end_time = request.POST.get('end_time')
            event.venue = request.POST.get('venue')
            event.max_participants = request.POST.get('max_participants')
            event.fees = request.POST.get('fees', 0)
            event.is_published = request.POST.get('is_published') == 'on'
            
            if request.FILES.get('image'):
                event.image = request.FILES.get('image')
            
            event.save()
            log_action(request, 'update', 'Event', event.title, object_id=pk)
            messages.success(request, f'Event "{event.title}" updated successfully.')
            return redirect('event_list')
        except Exception as e:
            messages.error(request, f'Error updating event: {str(e)}')

    context = {
        'event': event,
        'event_types': Event.EVENT_TYPE_CHOICES,
        'is_edit': True
    }
    return render(request, 'events/event_form.html', context)


@role_required('events_manage')
@require_http_methods(["POST"])
def toggle_event_publish(request, pk):
    """Toggle event publish status."""
    
    event = get_object_or_404(Event, pk=pk)
    event.is_published = not event.is_published
    event.save(update_fields=['is_published'])
    state = 'published' if event.is_published else 'hidden'
    messages.success(request, f'Event "{event.title}" {state}.')
    return redirect('event_list')

@role_required('events_manage')
@require_pin_auth('event_list')
def event_delete_view(request, pk):
    """Delete an event."""
    
    event = get_object_or_404(Event, pk=pk)
    
    if request.method == 'POST':
        title = event.title
        event_id = event.id
        event.delete()
        log_action(request, 'delete', 'Event', title, object_id=event_id)
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
            return JsonResponse({'status': 'ok', 'redirect_url': '/en/events/'})
            
        messages.success(request, f'Event "{title}" deleted successfully.')
    
    return redirect('event_list')


@role_required('events_manage')
def event_registrations_view(request, pk):
    """Admin view to list all registrations for an event."""
    event = get_object_or_404(Event, pk=pk)
    query = request.GET.get('q', '')
    registrations = event.registrations.all()

    if query:
        registrations = registrations.filter(
            Q(full_name__icontains=query) |
            Q(email__icontains=query) |
            Q(phone__icontains=query)
        )
    
    registrations = registrations.order_by('-registered_at')
    
    # Pagination
    paginator = Paginator(registrations, 20)  # Show 20 registrations per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    from django.urls import reverse
    context = {
        'event': event,
        'registrations': page_obj,
        'search_query': query,
        'export_event_registrations_excel_url': reverse('export_event_registrations_excel', kwargs={'pk': pk}),
        'export_event_registrations_csv_url': reverse('export_event_registrations_csv', kwargs={'pk': pk}),
        'export_event_registrations_pdf_url': reverse('export_event_registrations_pdf', kwargs={'pk': pk}),
        'export_event_registrations_copy_url': reverse('export_event_registrations_copy', kwargs={'pk': pk}),
        'export_event_registrations_print_url': reverse('export_event_registrations_print', kwargs={'pk': pk}),
    }
    
    if request.headers.get('HX-Request'):
        return render(request, 'events/partials/event_registrations_partial.html', context)

    return render(request, 'events/event_registrations.html', context)


@role_required('events_manage')
def event_feedback_admin_view(request, pk):
    """Admin view to list and publish/unpublish feedback for an event."""
    event = get_object_or_404(Event, pk=pk)
    feedbacks = event.feedbacks.all().order_by('-submitted_at')
    return render(request, 'events/event_feedback_admin.html', {
        'event': event,
        'feedbacks': feedbacks,
    })


@role_required('events_manage')
@require_http_methods(["POST"])
def toggle_event_feedback(request, pk):
    """Toggle the feedback_enabled field for an event."""
    event = get_object_or_404(Event, pk=pk)
    event.feedback_enabled = not event.feedback_enabled
    event.save(update_fields=['feedback_enabled'])
    state = 'enabled' if event.feedback_enabled else 'disabled'
    messages.success(request, f'Feedback form {state} for "{event.title}".')
    return redirect('event_feedback_admin', pk=pk)


@role_required('events_manage')
@require_http_methods(["POST"])
def toggle_feedback_publish(request, feedback_pk):
    """Toggle publish/unpublish for a single feedback entry."""
    feedback = get_object_or_404(EventFeedback, pk=feedback_pk)
    feedback.is_published = not feedback.is_published
    feedback.save(update_fields=['is_published'])
    state = 'published' if feedback.is_published else 'unpublished'
    messages.success(request, f'Feedback by {feedback.reviewer_name} {state}.')
    return redirect('event_feedback_admin', pk=feedback.event_id)

# ── Export Logic ──

def _get_filtered_events(request):
    query = request.GET.get('q', '')
    events = Event.objects.all().order_by('date', 'start_time')
    if query:
        events = events.filter(Q(title__icontains=query) | Q(venue__icontains=query))
    return events, query

def _event_mapping(e):
    return [e.title, e.get_event_type_display(), e.date.strftime('%Y-%m-%d'), e.venue, f"{e.registrations.count()}/{e.max_participants or '∞'}", float(e.fees)]

@role_required('events_manage')
def export_events_excel(request):
    events, _ = _get_filtered_events(request)
    headers = ["Title", "Type", "Date", "Venue", "Participants", "Fees"]
    return SpinalCureExport.to_excel(events, headers, _event_mapping, "Events", "events")

@role_required('events_manage')
def export_events_csv(request):
    events, _ = _get_filtered_events(request)
    headers = ["Title", "Type", "Date", "Venue", "Participants", "Fees"]
    return SpinalCureExport.to_csv(events, headers, _event_mapping, "events")

@role_required('events_manage')
def export_events_pdf(request):
    events, query = _get_filtered_events(request)
    headers = ["Title", "Type", "Date", "Venue", "Participants", "Fees"]
    def pdf_mapping(e):
        return [e.title, e.get_event_type_display(), e.date.strftime('%b %d, %Y'), e.venue, f"{e.registrations.count()}/{e.max_participants or '∞'}", f"₹{e.fees:,.2f}"]
    title = f"Events Schedule {'(Filtered)' if query else ''}"
    return SpinalCureExport.to_pdf(events, headers, pdf_mapping, title, "events")

@role_required('events_manage')
def export_events_copy(request):
    events, _ = _get_filtered_events(request)
    headers = ["Title", "Type", "Date", "Venue", "Participants", "Fees"]
    text = SpinalCureExport.to_text(events, headers, _event_mapping)
    from django.http import HttpResponse
    return HttpResponse(text, content_type='text/plain')

@role_required('events_manage')
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
    return [r.full_name, r.email, r.phone, r.get_status_display(), r.created_at.strftime('%Y-%m-%d %H:%M')]

@role_required('events_manage')
def export_event_registrations_excel(request, pk):
    event = get_object_or_404(Event, pk=pk)
    registrations = event.registrations.all().order_by('-registered_at')
    headers = ["Name", "Email", "Phone", "Status", "Date"]
    return SpinalCureExport.to_excel(registrations, headers, _registration_mapping, f"Reg - {event.title[:20]}", "event_registrations")

@role_required('events_manage')
def export_event_registrations_csv(request, pk):
    event = get_object_or_404(Event, pk=pk)
    registrations = event.registrations.all().order_by('-registered_at')
    headers = ["Name", "Email", "Phone", "Status", "Date"]
    return SpinalCureExport.to_csv(registrations, headers, _registration_mapping, "event_registrations")

@role_required('events_manage')
def export_event_registrations_pdf(request, pk):
    event = get_object_or_404(Event, pk=pk)
    registrations = event.registrations.all().order_by('-registered_at')
    headers = ["Name", "Email", "Phone", "Status", "Date"]
    title = f"Registrations: {event.title}"
    return SpinalCureExport.to_pdf(registrations, headers, _registration_mapping, title, "event_registrations")

@role_required('events_manage')
def export_event_registrations_copy(request, pk):
    event = get_object_or_404(Event, pk=pk)
    registrations = event.registrations.all().order_by('-registered_at')
    headers = ["Name", "Email", "Phone", "Status", "Date"]
    text = SpinalCureExport.to_text(registrations, headers, _registration_mapping)
    from django.http import HttpResponse
    return HttpResponse(text, content_type='text/plain')

@role_required('events_manage')
def export_event_registrations_print(request, pk):
    event = get_object_or_404(Event, pk=pk)
    registrations = event.registrations.all().order_by('-registered_at')
    headers = ["Name", "Email", "Phone", "Status", "Date"]
    rows = [_registration_mapping(r) for r in registrations]
    context = {
        'rows': rows,
        'title': f'Registrations: {event.title}',
        'headers': headers,
        'now': datetime.now(),
    }
    return render(request, 'exports/print_template.html', context)
