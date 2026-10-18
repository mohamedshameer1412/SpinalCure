from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from spinalcure.decorators import role_required
from .models import EVENTS, Notification, NotificationPreference


@role_required('dashboard_view')
def center(request):
    box = request.GET.get('box', 'inbox')
    qs = request.user.notifications.filter(is_archived=(box == 'archived'))
    if box == 'unread':
        qs = qs.filter(is_read=False)
    page = Paginator(qs, 20).get_page(request.GET.get('page'))
    return render(request, 'notifications/center.html', {'page': page, 'box': box})


@role_required('dashboard_view')
def open_notification(request, pk):
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    if not n.is_read:
        n.is_read = True
        n.save(update_fields=['is_read'])
    return redirect(n.url if n.url.startswith('/') and not n.url.startswith('//') else 'notification_center')


@require_POST
@role_required('dashboard_view')
def bulk_action(request):
    action = request.POST.get('action')
    qs = request.user.notifications.all()
    if request.POST.get('id'):
        qs = qs.filter(pk=request.POST['id'])
    if action == 'read':
        qs.update(is_read=True)
    elif action == 'archive':
        qs.update(is_archived=True, is_read=True)
    elif action == 'unarchive':
        qs.update(is_archived=False)
    nxt = request.POST.get('next', '')
    return redirect(nxt if nxt.startswith('/') and not nxt.startswith('//') else 'notification_center')


@role_required('dashboard_view')
def preferences(request):
    current = {p.event: p for p in request.user.notification_prefs.all()}
    if request.method == 'POST':
        for key, _label in EVENTS:
            NotificationPreference.objects.update_or_create(user=request.user, event=key, defaults={
                'in_app': f'in_app_{key}' in request.POST, 'email': f'email_{key}' in request.POST})
        messages.success(request, 'Notification preferences saved.')
        return redirect('notification_preferences')
    rows = [(key, label, current[key].in_app if key in current else True, current[key].email if key in current else True)
            for key, label in EVENTS]
    return render(request, 'notifications/preferences.html', {'rows': rows})


@role_required('site_manage')
def deliveries(request):
    from .models import EmailOutbox
    from .services import deliver
    if request.method == 'POST':
        row = get_object_or_404(EmailOutbox, pk=request.POST.get('id'), status='failed')
        ok = deliver(row)
        (messages.success if ok else messages.error)(request, 'Email sent.' if ok else f'Still failing: {row.last_error}')
        return redirect('notification_deliveries')
    status = request.GET.get('status', '')
    qs = EmailOutbox.objects.all()
    if status in ('pending', 'sent', 'failed'):
        qs = qs.filter(status=status)
    page = Paginator(qs.defer('body_text', 'body_html', 'ics'), 30).get_page(request.GET.get('page'))
    return render(request, 'notifications/deliveries.html', {'page': page, 'status': status})
