"""
One entry point for notifications. Callers pass only non-sensitive text: no diagnoses,
notes or amounts beyond what the recipient already owns. Emails go through the outbox,
so failures are logged and retried by `manage.py send_notifications`.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import EVENT_KEYS, EmailOutbox, Notification, NotificationPreference

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 5


def _safe_url(url):
    return url if url.startswith('/') and not url.startswith('//') else ''


def deliver(row):
    """Try to send one outbox row; records the outcome. Never raises."""
    row.attempts += 1
    try:
        msg = EmailMultiAlternatives(row.subject, row.body_text, settings.DEFAULT_FROM_EMAIL, [row.to_email])
        if row.body_html:
            msg.attach_alternative(row.body_html, 'text/html')
        if row.ics:
            msg.attach('invite.ics', row.ics, 'text/calendar')
        msg.send(fail_silently=False)
        row.status, row.sent_at, row.last_error = 'sent', timezone.now(), ''
    except Exception as e:  # SMTP down, bad config, rejected address...
        row.status, row.last_error = 'failed', str(e)[:500]
        logger.warning('Email %s to %s failed (attempt %s): %s', row.pk, row.event, row.attempts, e)
    row.save(update_fields=['status', 'attempts', 'last_error', 'sent_at'])
    return row.status == 'sent'


def queue_email(to_email, event, subject, text, html='', dedupe_key=None, ics=''):
    """Record an email and send it after the current transaction commits. Duplicate dedupe_key = no-op."""
    assert event in EVENT_KEYS, event
    if not to_email:
        return None
    try:
        with transaction.atomic():
            row = EmailOutbox.objects.create(to_email=to_email, event=event, subject=subject[:255],
                                             body_text=text, body_html=html, ics=ics, dedupe_key=dedupe_key)
    except IntegrityError:
        return None  # already queued
    transaction.on_commit(lambda: deliver(row))
    return row


def _prefs(users, event):
    rows = NotificationPreference.objects.filter(user__in=users, event=event)
    return {p.user_id: p for p in rows}


def notify_users(users, event, title, body='', url='', dedupe_key=None, email=True):
    """In-app notification (and email, if the user allows) for each active staff user."""
    assert event in EVENT_KEYS, event
    users = [u for u in users if u and u.is_active]
    prefs = _prefs(users, event)
    url = _safe_url(url)
    for u in users:
        p = prefs.get(u.pk)
        if p is None or p.in_app:
            if dedupe_key:
                Notification.objects.get_or_create(user=u, dedupe_key=dedupe_key, defaults=dict(
                    event=event, title=title[:200], body=body[:500], url=url))
            else:
                Notification.objects.create(user=u, event=event, title=title[:200], body=body[:500], url=url)
        if email and u.email and (p is None or p.email):
            link = f'\n\n{settings.SITE_URL}{url}' if url else ''
            queue_email(u.email, event, title, f'{body}{link}', dedupe_key=f'{dedupe_key}:{u.pk}' if dedupe_key else None)


def users_with_perm(perm):
    from accounts.models import CustomUser
    from accounts.roles import has_perm
    return [u for u in CustomUser.objects.filter(is_active=True) if has_perm(u, perm)]


def user_for_practitioner(practitioner):
    """Staff login linked to a practitioner profile (matched by email, as elsewhere)."""
    from accounts.models import CustomUser
    if not practitioner or not practitioner.email:
        return None
    return CustomUser.objects.filter(email__iexact=practitioner.email, is_active=True).first()


def retry_failed():
    sent = 0
    from datetime import timedelta
    from django.db.models import Q
    stale = timezone.now() - timedelta(minutes=5)  # fresh pending rows are still being sent by their request
    rows = EmailOutbox.objects.filter(Q(status='failed') | Q(status='pending', created_at__lt=stale), attempts__lt=MAX_ATTEMPTS)
    for row in rows:
        sent += deliver(row)
    return sent
