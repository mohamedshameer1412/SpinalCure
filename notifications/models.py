"""In-app notifications, per-user preferences and the email outbox (delivery log + retries)."""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

EVENTS = [
    ('appointment_booked', _('Appointment booked')),
    ('appointment_confirmed', _('Appointment confirmed')),
    ('appointment_rescheduled', _('Appointment rescheduled')),
    ('appointment_cancelled', _('Appointment cancelled')),
    ('appointment_reminder', _('Upcoming appointment reminder')),
    ('appointment_missed', _('Missed appointment')),
    ('followup_due', _('Treatment follow-up due')),
    ('payment_received', _('Payment received')),
    ('invoice_created', _('Invoice created')),
    ('staff_invited', _('Staff invitation')),
    ('idcard_issued', _('ID card issued')),
    ('idcard_revoked', _('ID card revoked')),
    ('event_registration', _('Event / course registration')),
    ('event_changed', _('Event changed or cancelled')),
    ('admin_alert', _('Administrative alert')),
]
EVENT_KEYS = {k for k, _l in EVENTS}


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    event = models.CharField(max_length=40, choices=EVENTS)
    title = models.CharField(max_length=200)
    body = models.CharField(max_length=500, blank=True)
    url = models.CharField(max_length=300, blank=True)  # internal path only
    is_read = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    # NULL allows many; a value is unique per user, so retries/re-runs never duplicate.
    dedupe_key = models.CharField(max_length=120, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('user', 'dedupe_key')]
        indexes = [models.Index(fields=['user', 'is_archived', 'is_read'])]

    def __str__(self):
        return self.title


class NotificationPreference(models.Model):
    """Missing row = both channels on."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_prefs')
    event = models.CharField(max_length=40, choices=EVENTS)
    in_app = models.BooleanField(default=True)
    email = models.BooleanField(default=True)

    class Meta:
        unique_together = [('user', 'event')]


class EmailOutbox(models.Model):
    STATUS = [('pending', _('Pending')), ('sent', _('Sent')), ('failed', _('Failed'))]
    to_email = models.EmailField()
    event = models.CharField(max_length=40, choices=EVENTS)
    subject = models.CharField(max_length=255)
    body_text = models.TextField()
    body_html = models.TextField(blank=True)
    ics = models.TextField(blank=True)  # optional calendar invite attachment
    status = models.CharField(max_length=10, choices=STATUS, default='pending', db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)
    dedupe_key = models.CharField(max_length=160, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Email delivery')
        verbose_name_plural = _('Email deliveries')

    def __str__(self):
        return f'{self.event} -> {self.to_email} ({self.status})'
