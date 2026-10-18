"""
Central notification dispatch.

    notify('appointment_booked', patient=p, context={...}, url='/...', dedupe_key='appt:<id>:booked')

* Never raises into the caller: a notification failure must not roll back a booking or payment.
* `dedupe_key` makes retries/duplicate triggers idempotent (DB-enforced unique).
* Each external channel is a NotificationDelivery with retry/backoff and an atomic claim, so two
  workers can never send the same delivery twice.
* Sensitive clinical detail never goes into message text (see messages.py).
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from spinalcure.rbac import CAPABILITIES

from . import channels as channel_mod
from .events import EXTERNAL_CHANNELS, IN_APP, get_event
from .messages import render
from .models import Notification, NotificationDelivery, NotificationPreference

logger = logging.getLogger(__name__)

RETRY_DELAYS = [timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2), timedelta(hours=12)]
SUPPORTED_LANGUAGES = {code for code, _name in settings.LANGUAGES}


def safe_local_url(url):
    """Only same-site paths are allowed as deep links (no open redirects)."""
    if not url:
        return ''
    if url.startswith('/') and not url.startswith('//') and '\\' not in url:
        return url[:300]
    return ''


def _language(user, patient):
    lang = getattr(user, 'language', None) or getattr(patient, 'preferred_language', None) or 'en'
    return lang if lang in SUPPORTED_LANGUAGES else 'en'


def _address(channel, user, patient, email):
    if channel == 'email':
        return (getattr(user, 'email', '') or getattr(patient, 'email', '') or email or '').strip()
    if channel == 'sms':
        return (getattr(user, 'phone', '') or getattr(patient, 'phone', '') or '').strip()
    if channel == 'whatsapp':
        return (getattr(patient, 'whatsapp_no', '') or getattr(patient, 'phone', '') or '').strip()
    return ''


def resolve_channels(spec, user=None, patient=None, email=''):
    """Channels this recipient should receive `spec` on, after preferences."""
    wanted = set(spec.default_channels)
    if user is not None and spec.configurable:
        prefs = {(p.event_type, p.channel): p.enabled for p in NotificationPreference.objects.filter(
            user=user, event_type__in=[spec.key, '*'])}
        for channel in {c for (_e, c) in prefs} | wanted:
            decided = prefs.get((spec.key, channel), prefs.get(('*', channel)))
            if decided is True:
                wanted.add(channel)
            elif decided is False:
                wanted.discard(channel)
    if patient is not None:
        # Patients opt in per channel on their record; email defaults on.
        if not getattr(patient, 'notify_email', True):
            wanted.discard('email')
        if not getattr(patient, 'notify_sms', False):
            wanted.discard('sms')
        if not getattr(patient, 'notify_whatsapp', False):
            wanted.discard('whatsapp')
    if user is None and patient is None:  # guest: email only
        wanted = {'email'} if 'email' in wanted else set()
    return wanted


def notify(event_key, *, user=None, patient=None, email='', context=None, url='', dedupe_key=''):
    """Create a notification and queue its deliveries. Returns the Notification (or None)."""
    try:
        spec = get_event(event_key)
        if user is None and patient is None and not email:
            return None
        if dedupe_key:
            existing = Notification.objects.filter(dedupe_key=dedupe_key).first()
            if existing:
                return existing
        language = _language(user, patient)
        title, body = render(event_key, context or {}, language)
        channels = resolve_channels(spec, user, patient, email)
        with transaction.atomic():
            notification = Notification.objects.create(
                user=user, patient=patient, email=email or '', event_type=event_key, level=spec.level,
                title=title, body=body, url=safe_local_url(url), language=language,
                persistent=spec.persistent, dedupe_key=dedupe_key,
            )
            for channel in EXTERNAL_CHANNELS:
                if channel in channels:
                    to = _address(channel, user, patient, email)
                    NotificationDelivery.objects.create(
                        notification=notification, channel=channel, to_address=to,
                        status=NotificationDelivery.PENDING if to else NotificationDelivery.SKIPPED,
                        last_error='' if to else 'No address on file',
                    )
        if getattr(settings, 'NOTIFY_SEND_ON_COMMIT', True):
            transaction.on_commit(lambda: deliver_notification(notification.pk))
        return notification
    except IntegrityError:
        # A concurrent request created the same dedupe_key first: that is the desired outcome.
        return Notification.objects.filter(dedupe_key=dedupe_key).first() if dedupe_key else None
    except Exception:
        logger.exception('notify(%s) failed', event_key)
        return None


def notify_staff(event_key, capability, *, context=None, url='', dedupe_key=''):
    """Fan out to every active user holding `capability`; dedupe is per recipient."""
    roles = CAPABILITIES.get(capability, set())
    User = get_user_model()
    from django.db.models import Q
    users = User.objects.filter(is_active=True).filter(Q(role__in=roles) | Q(is_superuser=True))
    return [n for n in (
        notify(event_key, user=u, context=context, url=url, dedupe_key=f'{dedupe_key}:{u.pk}' if dedupe_key else '')
        for u in users) if n]


def resolve_alert(dedupe_key_prefix):
    """Mark persistent alerts resolved once the underlying problem is fixed."""
    return Notification.objects.filter(
        dedupe_key__startswith=dedupe_key_prefix, persistent=True, resolved_at__isnull=True
    ).update(resolved_at=timezone.now())


def deliver_notification(notification_id):
    for delivery in NotificationDelivery.objects.filter(
            notification_id=notification_id, status=NotificationDelivery.PENDING):
        deliver(delivery.pk)


def deliver(delivery_id):
    """Attempt one delivery. Safe to call concurrently: only one caller wins the claim."""
    now = timezone.now()
    delivery = NotificationDelivery.objects.select_related('notification').filter(pk=delivery_id).first()
    if not delivery or delivery.status in (NotificationDelivery.SENT, NotificationDelivery.SKIPPED):
        return delivery
    if delivery.status == NotificationDelivery.FAILED and (
            delivery.next_attempt_at is None or delivery.next_attempt_at > now):
        return delivery
    claimed = NotificationDelivery.objects.filter(
        pk=delivery.pk, attempts=delivery.attempts, status__in=[NotificationDelivery.PENDING, NotificationDelivery.FAILED]
    ).update(attempts=delivery.attempts + 1, next_attempt_at=None)
    if not claimed:
        return delivery  # another worker has it
    delivery.refresh_from_db()
    try:
        if not delivery.to_address:
            raise channel_mod.RecipientUnavailable('No address on file')
        channel_mod.SENDERS[delivery.channel](delivery.notification, delivery.to_address)
        delivery.status, delivery.sent_at, delivery.last_error = NotificationDelivery.SENT, timezone.now(), ''
    except (channel_mod.ChannelNotConfigured, channel_mod.RecipientUnavailable) as exc:
        delivery.status, delivery.last_error = NotificationDelivery.SKIPPED, str(exc)[:500]
    except Exception as exc:  # network / SMTP / provider errors: retry with backoff
        delivery.status = NotificationDelivery.FAILED
        delivery.last_error = f'{type(exc).__name__}: {exc}'[:500]
        index = delivery.attempts - 1
        delivery.next_attempt_at = (timezone.now() + RETRY_DELAYS[index]) if index < len(RETRY_DELAYS) else None
        logger.warning('Notification delivery %s via %s failed (attempt %s): %s',
                       delivery.notification_id, delivery.channel, delivery.attempts, type(exc).__name__)
    delivery.save()
    return delivery


def retry_due():
    """Entry point for the `process_notifications` command; returns number attempted."""
    now = timezone.now()
    due = NotificationDelivery.objects.filter(
        status__in=[NotificationDelivery.PENDING, NotificationDelivery.FAILED]
    ).filter(next_attempt_at__lte=now) | NotificationDelivery.objects.filter(
        status=NotificationDelivery.PENDING, next_attempt_at__isnull=True,
        created_at__lte=now - timedelta(minutes=2))
    count = 0
    for delivery in due.distinct():
        deliver(delivery.pk)
        count += 1
    return count
