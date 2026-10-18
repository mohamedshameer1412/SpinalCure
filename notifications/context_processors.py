def notifications(request):
    """Initial unread count + open alert banners for staff; the bell then polls /notifications/summary/."""
    user = getattr(request, 'user', None)
    if not (user and user.is_authenticated):
        return {}
    from .models import Notification
    inbox = Notification.objects.filter(user=user, archived_at__isnull=True)
    return {
        'notif_unread': inbox.filter(read_at__isnull=True).count(),
        'notif_alerts': list(inbox.filter(persistent=True, resolved_at__isnull=True)[:3]),
    }
