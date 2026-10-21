import secrets
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from patients.models import Patient
from clinic.models import Practitioner
from spinalcure.validators import validate_time_range


class DoctorAvailability(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    """
    Doctor availability schedule - defines working hours for practitioners.
    """
    DAY_CHOICES = [
        (0, _('Monday')), (1, _('Tuesday')), (2, _('Wednesday')),
        (3, _('Thursday')), (4, _('Friday')), (5, _('Saturday')), (6, _('Sunday')),
    ]

    practitioner = models.ForeignKey(
        Practitioner,
        on_delete=models.CASCADE,
        related_name='availability',
        db_index=True
    )
    day_of_week = models.IntegerField(
        choices=DAY_CHOICES,
        verbose_name=_('Day'),
        db_index=True
    )
    start_time = models.TimeField(verbose_name=_('Start Time'))
    end_time = models.TimeField(verbose_name=_('End Time'))
    is_available = models.BooleanField(default=True, verbose_name=_('Available'), db_index=True)
    slot_duration_minutes = models.PositiveIntegerField(
        default=30,
        verbose_name=_('Slot Duration (mins)'),
        help_text='Duration of each appointment slot in minutes'
    )
    appointment_type = models.CharField(
        max_length=10, default='both', verbose_name=_('Applies to'),
        choices=[('both', _('In-person and online')), ('physical', _('In-person only')), ('online', _('Online only'))])
    buffer_minutes = models.PositiveIntegerField(
        default=0, verbose_name=_('Buffer between appointments (mins)'))
    break_start = models.TimeField(null=True, blank=True, verbose_name=_('Break start'))
    break_end = models.TimeField(null=True, blank=True, verbose_name=_('Break end'))
    max_appointments = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_('Max appointments in this shift'))
    valid_from = models.DateField(null=True, blank=True, verbose_name=_('Effective from'))
    valid_until = models.DateField(null=True, blank=True, verbose_name=_('Effective until'))

    class Meta:
        verbose_name = _('Doctor Availability')
        verbose_name_plural = _('Doctor Availabilities')
        ordering = ['practitioner', 'day_of_week', 'start_time']
        indexes = [
            models.Index(fields=['day_of_week', 'is_available']),
        ]

    def __str__(self):
        return f"{self.practitioner.name} — {self.get_day_of_week_display()}"

    def clean(self):
        """Validate time range, break, slot size and overlap with this practitioner's other shifts."""
        validate_time_range(self.start_time, self.end_time)
        if bool(self.break_start) != bool(self.break_end):
            raise ValidationError({'break_start': _('Set both break start and break end, or neither.')})
        if self.break_start:
            if not (self.start_time < self.break_start < self.break_end < self.end_time):
                raise ValidationError({'break_start': _('The break must fall inside the shift.')})
        if self.slot_duration_minutes < 5 or self.slot_duration_minutes > 480:
            raise ValidationError({'slot_duration_minutes': _('Slot duration must be between 5 and 480 minutes.')})
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValidationError({'valid_until': _('End date cannot be before the start date.')})
        if not self.practitioner_id:
            return
        others = DoctorAvailability.objects.filter(
            practitioner_id=self.practitioner_id, day_of_week=self.day_of_week, is_available=True,
            start_time__lt=self.end_time, end_time__gt=self.start_time).exclude(pk=self.pk)
        for other in others:
            if other.appointment_type in ('both', self.appointment_type) or self.appointment_type == 'both':
                if (not other.valid_until or not self.valid_from or other.valid_until >= self.valid_from) and \
                        (not self.valid_until or not other.valid_from or self.valid_until >= other.valid_from):
                    raise ValidationError(_('This shift overlaps another shift on the same day.'))


class TimeOff(models.Model):
    """Leave, holidays and closures. practitioner=None closes the whole clinic."""
    KIND_CHOICES = [('leave', _('Leave')), ('holiday', _('Holiday / closure')), ('other', _('Other'))]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    practitioner = models.ForeignKey(Practitioner, null=True, blank=True, on_delete=models.CASCADE,
                                     related_name='time_off', help_text=_('Leave empty to close the whole clinic.'))
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='leave')
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    start_time = models.TimeField(null=True, blank=True, help_text=_('Leave empty for the whole day.'))
    end_time = models.TimeField(null=True, blank=True)
    reason = models.CharField(max_length=200, blank=True, help_text=_('Internal only; never shown to patients.'))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_date', 'start_time']
        verbose_name = _('Time off')
        verbose_name_plural = _('Time off')

    def __str__(self):
        who = self.practitioner.name if self.practitioner_id else 'Clinic'
        return f'{who}: {self.start_date}–{self.end_date}'

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError({'end_date': _('End date cannot be before the start date.')})
        if bool(self.start_time) != bool(self.end_time):
            raise ValidationError({'start_time': _('Set both times, or leave both empty for a full day.')})
        if self.start_time and self.start_date == self.end_date and self.start_time >= self.end_time:
            raise ValidationError({'end_time': _('End time must be after start time.')})


class BookingSettings(models.Model):
    """Single-clinic booking rules. Use BookingSettings.get()."""
    min_notice_minutes = models.PositiveIntegerField(default=60, verbose_name=_('Minimum notice (mins)'))
    max_advance_days = models.PositiveIntegerField(default=90, verbose_name=_('Book at most this many days ahead'))
    default_duration_minutes = models.PositiveIntegerField(default=30)
    cancel_cutoff_hours = models.PositiveIntegerField(
        default=2, verbose_name=_('Patients may cancel/reschedule until (hours before)'))
    max_active_per_contact = models.PositiveIntegerField(
        default=3, verbose_name=_('Max upcoming public bookings per phone/email'))
    allow_public_booking = models.BooleanField(default=True)
    reminder_offsets_minutes = models.CharField(
        max_length=100, default='1440,120', verbose_name=_('Send reminders this many minutes before (comma-separated)'))
    followup_lead_days = models.PositiveIntegerField(default=2, verbose_name=_('Follow-up reminder lead (days)'))
    review_request_after_sessions = models.PositiveSmallIntegerField(
        default=3, verbose_name=_('Ask for a review after this many sessions'),
        help_text=_('One email per patient, sent the day after the session. 0 turns it off.'))
    missed_grace_minutes = models.PositiveIntegerField(default=60)
    auto_mark_no_show = models.BooleanField(
        default=False, verbose_name=_('Automatically mark unattended appointments as no-show'))

    class Meta:
        verbose_name = _('Booking settings')
        verbose_name_plural = _('Booking settings')

    @classmethod
    def get(cls):
        obj = cls.objects.order_by('pk').first()
        return obj or cls.objects.create()

    @property
    def reminder_offsets(self):
        out = []
        for part in (self.reminder_offsets_minutes or '').split(','):
            part = part.strip()
            if part.isdigit() and int(part) > 0:
                out.append(int(part))
        return sorted(set(out), reverse=True)

    def clean(self):
        bad = [p for p in (self.reminder_offsets_minutes or '').split(',') if p.strip() and not p.strip().isdigit()]
        if bad:
            raise ValidationError({'reminder_offsets_minutes': _('Use whole numbers of minutes separated by commas.')})


class Appointment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    """
    Patient appointments for treatments.
    """
    STATUS_CHOICES = [
        ('scheduled', _('Scheduled')),
        ('confirmed', _('Confirmed')),
        ('completed', _('Completed')),
        ('cancelled', _('Cancelled')),
        ('no_show', _('No Show')),
        ('rescheduled', _('Rescheduled')),
    ]

    TYPE_CHOICES = [
        ('physical', _('Physical Visit')),
        ('online', _('Online Call / Enquiry')),
    ]

    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='appointments',
        verbose_name=_('Patient'),
        db_index=True,
        db_constraint=False
    )
    
    # Guest / Lead details (used when booked online before becoming a patient)
    guest_name = models.CharField(_('Guest Name'), max_length=255, blank=True, null=True)
    guest_phone = models.CharField(_('Guest Phone'), max_length=20, blank=True, null=True)
    guest_email = models.EmailField(_('Guest Email'), blank=True, null=True)
    practitioner = models.ForeignKey(
        Practitioner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='appointments',
        verbose_name=_('Practitioner'),
        db_index=True
    )
    appointment_date = models.DateField(
        verbose_name=_('Date'),
        db_index=True
    )
    appointment_time = models.TimeField(verbose_name=_('Time'))
    duration_minutes = models.PositiveIntegerField(
        default=30,
        verbose_name=_('Duration (mins)')
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='scheduled',
        verbose_name=_('Status'),
        db_index=True
    )
    appointment_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default='physical',
        verbose_name=_('Appointment Type'),
        db_index=True
    )
    reason = models.CharField(max_length=300, blank=True, verbose_name=_('Reason for Visit'))
    notes = models.TextField(blank=True, verbose_name=_('Notes'))
    email_reminder_sent = models.BooleanField(
        default=False,
        verbose_name=_('Reminder Sent')
    )
    SOURCE_CHOICES = [('staff', _('Staff')), ('public', _('Public website')), ('portal', _('Patient portal')),
                      ('api', _('API'))]
    booked_via = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='staff')
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=300, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='+')
    rescheduled_from = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL,
                                         related_name='rescheduled_to')
    manage_token = models.CharField(
        max_length=43, unique=True, editable=False, default=secrets.token_urlsafe,
        help_text=_('Secret for the self-service cancel/reschedule link.'))
    request_key = models.CharField(
        max_length=64, null=True, blank=True, unique=True, editable=False,
        help_text=_('Idempotency key: a retried request cannot create a second booking.'))

    OCCUPYING = ('scheduled', 'confirmed', 'completed')
    TRANSITIONS = {
        'scheduled': {'confirmed', 'cancelled', 'rescheduled', 'no_show', 'completed'},
        'confirmed': {'cancelled', 'rescheduled', 'no_show', 'completed'},
        'completed': set(), 'cancelled': set(), 'no_show': set(), 'rescheduled': set(),
    }

    class Meta:
        verbose_name = _('Appointment')
        verbose_name_plural = _('Appointments')
        ordering = ['appointment_date', 'appointment_time']
        indexes = [
            models.Index(fields=['patient', 'appointment_date']),
            models.Index(fields=['status', 'appointment_date']),
            models.Index(fields=['practitioner', 'appointment_date']),
        ]
        constraints = [
            # Backstop against two live bookings starting at the same instant. Partial-overlap protection
            # is enforced under a row lock in appointments.scheduling.book() (MySQL has no partial indexes).
            models.UniqueConstraint(
                fields=['practitioner', 'appointment_date', 'appointment_time'],
                condition=Q(status__in=['scheduled', 'confirmed', 'completed']),
                name='appt_no_exact_double_booking'),
        ]

    def __str__(self):
        return f"{self.display_name} — {self.appointment_date} {self.appointment_time}"

    @property
    def display_name(self):
        return self.patient.name if self.patient_id and self.patient else (self.guest_name or 'Guest')

    @property
    def starts_at(self):
        naive = datetime.combine(self.appointment_date, self.appointment_time)
        return timezone.make_aware(naive, timezone.get_default_timezone())

    @property
    def ends_at(self):
        return self.starts_at + timedelta(minutes=self.duration_minutes)

    def can_transition(self, new_status):
        return new_status in self.TRANSITIONS.get(self.status, set())

    @property
    def status_display(self):
        """Get display name for status."""
        return dict(self.STATUS_CHOICES).get(self.status, self.status)

