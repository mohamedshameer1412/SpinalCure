import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .events import CHANNELS, EVENT_CHOICES, EXTERNAL_CHANNELS, LEVELS


class Notification(models.Model):
    """One message for one recipient (a clinic user, a patient, or a bare email address)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
                             related_name='notifications')
    patient = models.ForeignKey('patients.Patient', null=True, blank=True, on_delete=models.CASCADE,
                                related_name='notifications', db_constraint=False)
    email = models.EmailField(blank=True, help_text=_('Guest recipient with no account.'))
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES, db_index=True)
    level = models.CharField(max_length=10, choices=[(l, l) for l in LEVELS], default='info')
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=300, blank=True, help_text=_('Local deep link, e.g. /appointments/'))
    language = models.CharField(max_length=5, default='en')
    persistent = models.BooleanField(default=False, db_index=True)
    dedupe_key = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'read_at', 'archived_at']),
            models.Index(fields=['persistent', 'resolved_at']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['dedupe_key'], condition=~Q(dedupe_key=''), name='notif_unique_dedupe'),
            models.CheckConstraint(
                check=Q(user__isnull=False) | Q(patient__isnull=False) | ~Q(email=''),
                name='notif_has_recipient'),
        ]

    def __str__(self):
        return f'{self.event_type}: {self.title}'

    @property
    def is_read(self):
        return self.read_at is not None

    @property
    def is_active_alert(self):
        return self.persistent and self.resolved_at is None and self.archived_at is None

    def mark_read(self):
        if not self.read_at:
            self.read_at = timezone.now()
            self.save(update_fields=['read_at'])


class NotificationDelivery(models.Model):
    """Per-channel delivery attempt state, retried with backoff."""
    PENDING, SENT, FAILED, SKIPPED = 'pending', 'sent', 'failed', 'skipped'
    STATUS_CHOICES = [(PENDING, _('Pending')), (SENT, _('Sent')), (FAILED, _('Failed')), (SKIPPED, _('Skipped'))]

    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='deliveries')
    channel = models.CharField(max_length=10, choices=[(c, c) for c in EXTERNAL_CHANNELS])
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING, db_index=True)
    to_address = models.CharField(max_length=254, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['notification', 'channel'], name='delivery_one_per_channel'),
        ]

    def __str__(self):
        return f'{self.notification_id}/{self.channel}: {self.status}'


class NotificationPreference(models.Model):
    """User override for (event, channel). event_type '*' applies to every event."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_prefs')
    event_type = models.CharField(max_length=40)
    channel = models.CharField(max_length=10, choices=[(c, c) for c in CHANNELS])
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'event_type', 'channel'], name='notif_pref_unique'),
        ]
