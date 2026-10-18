from django.utils.functional import SimpleLazyObject


def bell(request):
    """Unread count and latest items for the top-bar bell; lazy, so pages that don't render it pay nothing."""
    def load():
        u = request.user
        if not getattr(u, 'is_authenticated', False):
            return {'unread': 0, 'recent': []}
        qs = u.notifications.filter(is_archived=False)
        return {'unread': qs.filter(is_read=False).count(), 'recent': list(qs[:6])}
    return {'notif': SimpleLazyObject(load)}
