from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from spinalcure.rbac import require_capability

from .events import CHANNELS, EVENTS
from .models import Notification, NotificationDelivery, NotificationPreference
from .service import deliver, safe_local_url

TABS = ('all', 'unread', 'alerts', 'archived')


def _mine(request):
    return Notification.objects.filter(user=request.user)


def _inbox(request):
    return _mine(request).filter(archived_at__isnull=True)


@login_required
def center(request):
    tab = request.GET.get('tab', 'all')
    if tab not in TABS:
        tab = 'all'
    qs = _inbox(request)
    if tab == 'unread':
        qs = qs.filter(read_at__isnull=True)
    elif tab == 'alerts':
        qs = qs.filter(persistent=True, resolved_at__isnull=True)
    elif tab == 'archived':
        qs = _mine(request).filter(archived_at__isnull=False)
    page = Paginator(qs, 20).get_page(request.GET.get('page'))
    ctx = {
        'page': page, 'tab': tab, 'tabs': TABS,
        'unread_count': _inbox(request).filter(read_at__isnull=True).count(),
    }
    template = 'notifications/_list.html' if request.headers.get('HX-Request') else 'notifications/center.html'
    return render(request, template, ctx)


@login_required
@require_GET
def summary(request):
    """Polled by the bell: unread count, latest items, open alerts."""
    inbox = _inbox(request)
    latest = list(inbox.order_by('-created_at')[:8])
    prefs = NotificationPreference.objects.filter(user=request.user, channel='browser', enabled=True).exists()
    return JsonResponse({
        'unread': inbox.filter(read_at__isnull=True).count(),
        'alerts': inbox.filter(persistent=True, resolved_at__isnull=True).count(),
        'browser_enabled': prefs,
        'items': [{
            'id': str(n.pk), 'title': n.title, 'body': n.body, 'level': n.level, 'read': n.is_read,
            'persistent': n.persistent, 'created': n.created_at.isoformat(),
            'open_url': reverse('notification_open', args=[n.pk]) if n.url else '',
        } for n in latest],
    })


def _respond(request, fallback='notification_center'):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('HX-Request'):
        return JsonResponse({'status': 'ok', 'unread': _inbox(request).filter(read_at__isnull=True).count()})
    return redirect(safe_local_url(request.POST.get('next', '')) or fallback)


@login_required
@require_POST
def mark_read(request, pk):
    get_object_or_404(_mine(request), pk=pk).mark_read()
    return _respond(request)


@login_required
@require_POST
def mark_unread(request, pk):
    _mine(request).filter(pk=pk).update(read_at=None)
    return _respond(request)


@login_required
@require_POST
def archive(request, pk):
    _mine(request).filter(pk=pk).update(archived_at=timezone.now(), read_at=timezone.now())
    return _respond(request)


@login_required
@require_POST
def unarchive(request, pk):
    _mine(request).filter(pk=pk).update(archived_at=None)
    return _respond(request)


@login_required
@require_POST
def mark_all_read(request):
    _inbox(request).filter(read_at__isnull=True).update(read_at=timezone.now())
    return _respond(request)


@login_required
def open_notification(request, pk):
    """Mark read and follow the (validated, same-site) deep link."""
    n = get_object_or_404(_mine(request), pk=pk)
    n.mark_read()
    return redirect(safe_local_url(n.url) or 'notification_center')


@login_required
def preferences(request):
    staff_events = [e for e in EVENTS.values() if e.audience == 'staff']
    channels = ['in_app', 'email', 'browser'] + (['sms'] if getattr(settings, 'NOTIFY_SMS_BACKEND', '') else [])
    if request.method == 'POST':
        if request.POST.get('language') in dict(settings.LANGUAGES):
            request.user.language = request.POST['language']
            request.user.save(update_fields=['language'])
        for e in staff_events:
            if not e.configurable:
                continue
            for c in channels:
                NotificationPreference.objects.update_or_create(
                    user=request.user, event_type=e.key, channel=c,
                    defaults={'enabled': request.POST.get(f'{e.key}__{c}') == 'on'})
        messages.success(request, _('Notification preferences saved.'))
        return redirect('notification_preferences')
    saved = {(p.event_type, p.channel): p.enabled for p in NotificationPreference.objects.filter(user=request.user)}
    rows = [{
        'event': e,
        'cells': [{'channel': c, 'name': f'{e.key}__{c}',
                   'checked': saved.get((e.key, c), c in e.default_channels), 'locked': not e.configurable}
                  for c in channels],
    } for e in staff_events]
    return render(request, 'notifications/preferences.html', {
        'rows': rows, 'channels': channels, 'languages': settings.LANGUAGES,
        'sms_available': bool(getattr(settings, 'NOTIFY_SMS_BACKEND', '')),
    })


@require_capability('notifications.admin')
def deliveries(request):
    status = request.GET.get('status', 'failed')
    qs = NotificationDelivery.objects.select_related('notification')
    if status in ('pending', 'sent', 'failed', 'skipped'):
        qs = qs.filter(status=status)
    page = Paginator(qs.order_by('-created_at'), 25).get_page(request.GET.get('page'))
    return render(request, 'notifications/deliveries.html', {
        'page': page, 'status': status, 'statuses': ['failed', 'pending', 'skipped', 'sent']})


@require_POST
@require_capability('notifications.admin')
def retry_delivery(request, pk):
    d = get_object_or_404(NotificationDelivery, pk=pk)
    if d.status == NotificationDelivery.FAILED:
        d.next_attempt_at = timezone.now()
        d.save(update_fields=['next_attempt_at'])
        result = deliver(d.pk)
        if result.status == NotificationDelivery.SENT:
            messages.success(request, _('Delivered.'))
        else:
            messages.error(request, _('Delivery still failing: %(e)s') % {'e': result.last_error[:120]})
    return redirect('notification_deliveries')
