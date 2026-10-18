import secrets
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Event(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    """
    Events, workshops, and seminars organized by the clinic.
    """
    EVENT_TYPE_CHOICES = [
        ('class', _('Class')),
        ('workshop', _('Workshop')),
        ('meeting', _('Meeting')),
        ('seminar', _('Seminar')),
        ('camp', _('Health Camp')),
        ('webinar', _('Webinar')),
        ('other', _('Other')),
    ]

    organizer = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='organized_events',
        verbose_name=_('Organizer')
    )
    clinic = models.ForeignKey(
        'clinic.ClinicProfile',
        on_delete=models.CASCADE,
        related_name='events',
        verbose_name=_('Clinic'),
        null=True,
        blank=True
    )

    title = models.CharField(
        max_length=300,
        verbose_name=_('Title'),
        db_index=True
    )
    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPE_CHOICES,
        default='class',
        verbose_name=_('Type'),
        db_index=True
    )
    description = models.TextField(blank=True, verbose_name=_('Description'))
    image = models.ImageField(
        upload_to='events/',
        blank=True,
        null=True,
        verbose_name=_('Banner Image')
    )
    date = models.DateField(
        verbose_name=_('Date'),
        db_index=True
    )
    start_time = models.TimeField(verbose_name=_('Start Time'))
    end_time = models.TimeField(verbose_name=_('End Time'))
    venue = models.CharField(
        max_length=300,
        blank=True,
        verbose_name=_('Venue')
    )
    is_online = models.BooleanField(
        default=False,
        verbose_name=_('Online Event'),
        db_index=True
    )
    meeting_link = models.URLField(
        blank=True, verbose_name=_('Meeting Link'),
        help_text=_('Private: shown only to confirmed registrants shortly before the event.'))
    meeting_provider = models.CharField(
        max_length=20, blank=True, verbose_name=_('Meeting provider'),
        choices=[('', _('Not specified')), ('zoom', 'Zoom'), ('google_meet', 'Google Meet'),
                 ('teams', 'Microsoft Teams'), ('jitsi', 'Jitsi'), ('other', _('Other'))])
    meeting_passcode = models.CharField(max_length=100, blank=True, verbose_name=_('Meeting passcode'))
    access_instructions = models.TextField(blank=True, verbose_name=_('Joining instructions'))
    STATUS_CHOICES = [('draft', _('Draft')), ('published', _('Published')), ('cancelled', _('Cancelled')),
                      ('archived', _('Archived'))]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft', db_index=True,
                              verbose_name=_('Status'))
    cancel_reason = models.CharField(max_length=300, blank=True)
    presenter = models.CharField(max_length=200, blank=True, verbose_name=_('Presenter / speaker'))
    timezone = models.CharField(max_length=64, default=settings.TIME_ZONE, verbose_name=_('Time zone'))
    language = models.CharField(
        max_length=5, default='en', verbose_name=_('Language'),
        choices=[('en', 'English'), ('ta', 'தமிழ்'), ('hi', 'हिन्दी'), ('ar', 'العربية')])
    registration_deadline = models.DateTimeField(null=True, blank=True, verbose_name=_('Registration deadline'))
    waitlist_enabled = models.BooleanField(default=True, verbose_name=_('Waitlist when full'))
    reminder_offsets_minutes = models.CharField(
        max_length=100, default='1440,60', verbose_name=_('Reminders (minutes before, comma-separated)'))
    updated_at = models.DateTimeField(auto_now=True, null=True)
    max_participants = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name=_('Max Participants')
    )
    is_published = models.BooleanField(
        default=False,
        verbose_name=_('Published'),
        db_index=True
    )
    feedback_enabled = models.BooleanField(
        default=False,
        verbose_name=_('Feedback Form Enabled'),
        help_text=_('Enable this after the event to allow attendees to leave feedback.'),
        db_index=True
    )
    registration_required = models.BooleanField(
        default=False,
        verbose_name=_('Registration Required')
    )
    fees = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        verbose_name=_('Fees (₹)')
    )

    class Meta:
        verbose_name = _('Event')
        verbose_name_plural = _('Events')
        ordering = ['date', 'start_time']
        indexes = [
            models.Index(fields=['is_published', 'date']),
            models.Index(fields=['event_type', 'date']),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_event_type_display()}) — {self.date}"

    # ── schedule (event time zone) ──────────────────────────────────────────────────────────────
    @property
    def tz(self):
        try:
            return ZoneInfo(self.timezone)
        except Exception:
            return timezone.get_default_timezone()

    @property
    def starts_at(self):
        return datetime.combine(self.date, self.start_time).replace(tzinfo=self.tz)

    @property
    def ends_at(self):
        return datetime.combine(self.date, self.end_time).replace(tzinfo=self.tz)

    @property
    def phase(self):
        """Where the event is in time: cancelled / upcoming / live / completed."""
        if self.status == 'cancelled':
            return 'cancelled'
        now = timezone.now()
        if now < self.starts_at:
            return 'upcoming'
        return 'live' if now <= self.ends_at else 'completed'

    @property
    def is_upcoming(self):
        return self.phase == 'upcoming'

    @property
    def is_past(self):
        return self.phase == 'completed'

    @property
    def duration_minutes(self):
        return int((self.ends_at - self.starts_at).total_seconds() // 60)

    @property
    def reminder_offsets(self):
        return sorted({int(x) for x in (self.reminder_offsets_minutes or '').replace(' ', '').split(',')
                       if x.isdigit() and int(x) > 0}, reverse=True)

    @property
    def confirmed_count(self):
        return self.registrations.filter(status='confirmed').count()

    @property
    def seats_left(self):
        if self.max_participants is None:
            return None
        return max(self.max_participants - self.confirmed_count, 0)

    @property
    def is_full(self):
        return self.max_participants is not None and self.confirmed_count >= self.max_participants

    def save(self, *args, **kwargs):
        # `status` is the source of truth; `is_published` stays in sync for existing queries/templates.
        self.is_published = self.status == 'published'
        super().save(*args, **kwargs)

    def clean(self):
        """Validate event data."""
        from spinalcure.validators import validate_time_range
        
        # Validate time range
        validate_time_range(self.start_time, self.end_time)
        
        if self.is_online and self.status == 'published' and not self.meeting_link:
            raise ValidationError({'meeting_link': _('Add the meeting link before publishing an online event.')})
        if not self.is_online and not self.venue:
            raise ValidationError({'venue': _('Venue is required for in-person events.')})
        try:
            ZoneInfo(self.timezone)
        except Exception:
            raise ValidationError({'timezone': _('Unknown time zone.')})
        if self._state.adding and self.date < date.today():
            raise ValidationError({'date': _('Cannot create an event in the past.')})
        if self.registration_deadline and self.registration_deadline > self.starts_at:
            raise ValidationError({'registration_deadline': _('The deadline must be before the event starts.')})
        bad = [p for p in (self.reminder_offsets_minutes or '').split(',') if p.strip() and not p.strip().isdigit()]
        if bad:
            raise ValidationError({'reminder_offsets_minutes': _('Use whole numbers of minutes separated by commas.')})
        if self.max_participants is not None and self.max_participants < 1:
            raise ValidationError({'max_participants': _('Capacity must be at least 1.')})


class EventRegistration(models.Model):
    """Registration submitted by a visitor for an event."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='registrations',
        verbose_name=_('Event')
    )
    name = models.CharField(max_length=200, verbose_name=_('Full Name'))
    phone = models.CharField(max_length=20, verbose_name=_('Phone Number'))
    email = models.EmailField(blank=True, verbose_name=_('Email'))
    notes = models.TextField(blank=True, verbose_name=_('Notes / Message'))
    registered_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Registered At'))
    STATUS_CHOICES = [('confirmed', _('Confirmed')), ('waitlisted', _('Waitlisted')), ('cancelled', _('Cancelled'))]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='confirmed', db_index=True)
    phone_key = models.CharField(max_length=15, blank=True, db_index=True, editable=False)
    language = models.CharField(max_length=5, default='en')
    access_token = models.CharField(max_length=43, unique=True, editable=False, default=secrets.token_urlsafe,
                                    help_text=_('Secret in the registrant\'s links: join, cancel, feedback.'))
    attended = models.BooleanField(default=False)
    attended_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    promoted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('Event Registration')
        verbose_name_plural = _('Event Registrations')
        ordering = ['-registered_at']
        indexes = [models.Index(fields=['event', 'status', 'registered_at'])]

    def __str__(self):
        return f"{self.name} — {self.event.title}"


class EventFeedback(models.Model):
    """Attendee feedback/review for an event. Only registered attendees can submit."""
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='feedbacks',
        verbose_name=_('Event')
    )
    registration = models.OneToOneField(
        'EventRegistration',
        on_delete=models.CASCADE,
        related_name='feedback',
        verbose_name=_('Registration'),
        null=True,
        blank=True,
        help_text=_('The registration this feedback belongs to.')
    )
    reviewer_name = models.CharField(max_length=200, verbose_name=_('Name'))
    rating = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES,
        verbose_name=_('Rating')
    )
    comment = models.TextField(verbose_name=_('Comment'))
    is_published = models.BooleanField(
        default=False,
        verbose_name=_('Published'),
        db_index=True
    )
    submitted_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Submitted At'))

    class Meta:
        verbose_name = _('Event Feedback')
        verbose_name_plural = _('Event Feedbacks')
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.reviewer_name} — {self.event.title} ({self.rating}★)"

