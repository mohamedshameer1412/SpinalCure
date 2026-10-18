from django.db import models
import uuid
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from datetime import date


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
    meeting_link = models.URLField(blank=True, verbose_name=_('Meeting Link'))
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
    presenter = models.CharField(max_length=200, blank=True, verbose_name=_('Presenter / Speaker'))
    language = models.CharField(max_length=5, blank=True, verbose_name=_('Language'),
                                choices=[('en', 'English'), ('ta', 'தமிழ்'), ('hi', 'हिन्दी'), ('ar', 'العربية')])
    registration_deadline = models.DateTimeField(null=True, blank=True, verbose_name=_('Registration closes'))
    waitlist_enabled = models.BooleanField(default=True, verbose_name=_('Waitlist when full'))
    is_cancelled = models.BooleanField(default=False, db_index=True, verbose_name=_('Cancelled'))
    cancel_reason = models.CharField(max_length=300, blank=True)
    is_archived = models.BooleanField(default=False, db_index=True, verbose_name=_('Archived'))
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

    # Times are clinic-local (settings.TIME_ZONE, Asia/Kolkata).
    @property
    def starts_at(self):
        from datetime import datetime
        from django.utils import timezone
        return timezone.make_aware(datetime.combine(self.date, self.start_time))

    @property
    def ends_at(self):
        from datetime import datetime
        from django.utils import timezone
        return timezone.make_aware(datetime.combine(self.date, self.end_time))

    @property
    def phase(self):
        """draft | cancelled | upcoming | live | completed (archived events keep their phase)."""
        from django.utils import timezone
        if self.is_cancelled:
            return 'cancelled'
        if not self.is_published:
            return 'draft'
        now = timezone.now()
        if now < self.starts_at:
            return 'upcoming'
        return 'live' if now <= self.ends_at else 'completed'

    @property
    def confirmed_count(self):
        return self.registrations.filter(status='confirmed').count()

    @property
    def seats_left(self):
        if not self.max_participants:
            return None
        return max(0, self.max_participants - self.confirmed_count)

    def registration_closed_reason(self):
        from django.utils import timezone
        if self.phase != 'upcoming':
            return 'Registration is closed for this event.'
        if self.registration_deadline and timezone.now() > self.registration_deadline:
            return 'The registration deadline has passed.'
        return None

    @property
    def is_upcoming(self):
        """Check if event is upcoming (not yet passed)."""
        return self.date >= date.today()

    @property
    def is_past(self):
        """Check if event has passed."""
        return self.date < date.today()

    def clean(self):
        """Validate event data."""
        from spinalcure.validators import validate_time_range
        
        # Validate time range
        validate_time_range(self.start_time, self.end_time)
        
        # Validate online event has meeting link
        if self.is_online and not self.meeting_link:
            raise ValidationError({
                'meeting_link': _('Meeting link is required for online events.')
            })
        
        # Validate venue for offline event
        if not self.is_online and not self.venue:
            raise ValidationError({
                'venue': _('Venue is required for offline events.')
            })
        
        # Validate date is not in the past for unpublished events
        if not self.is_published and self.date < date.today():
            raise ValidationError({
                'date': _('Cannot create event in the past.')
            })


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
    status = models.CharField(max_length=12, default='confirmed', db_index=True, choices=[
        ('confirmed', _('Confirmed')), ('waitlisted', _('Waitlisted')), ('cancelled', _('Cancelled'))])
    attended = models.BooleanField(null=True, blank=True, verbose_name=_('Attended'))
    # Private link for the registrant (status, cancel, join). Never shown publicly.
    access_token = models.CharField(max_length=40, unique=True, null=True, editable=False)

    class Meta:
        verbose_name = _('Event Registration')
        verbose_name_plural = _('Event Registrations')
        ordering = ['-registered_at']

    def save(self, *args, **kwargs):
        if not self.access_token:
            import secrets
            self.access_token = secrets.token_urlsafe(24)
        super().save(*args, **kwargs)

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

