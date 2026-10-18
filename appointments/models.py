from django.db import models
import uuid
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from patients.models import Patient
from clinic.models import Practitioner
from spinalcure.validators import validate_not_in_past, validate_time_range


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
    buffer_minutes = models.PositiveIntegerField(
        default=0, verbose_name=_('Buffer (mins)'), help_text=_('Gap kept free after each appointment')
    )
    max_appointments = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_('Max bookings in this shift'), help_text=_('Leave empty for no limit')
    )

    # Several rows per day are allowed (e.g. morning and evening shifts); the gap between them is the break.
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
        """Validate time range and that shifts on the same day do not overlap."""
        validate_time_range(self.start_time, self.end_time)
        overlapping = DoctorAvailability.objects.filter(
            practitioner_id=self.practitioner_id, day_of_week=self.day_of_week,
            start_time__lt=self.end_time, end_time__gt=self.start_time,
        ).exclude(pk=self.pk)
        if overlapping.exists():
            raise ValidationError(_('This shift overlaps another shift on the same day.'))


class PractitionerLeave(models.Model):
    """Leave for one practitioner, or a clinic holiday when practitioner is empty. Dates inclusive."""
    practitioner = models.ForeignKey(
        Practitioner, on_delete=models.CASCADE, null=True, blank=True, related_name='leaves',
        verbose_name=_('Practitioner'), help_text=_('Leave empty for a clinic-wide holiday')
    )
    start_date = models.DateField(verbose_name=_('From'))
    end_date = models.DateField(verbose_name=_('To'))
    reason = models.CharField(max_length=200, blank=True, verbose_name=_('Reason'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Leave / Holiday')
        verbose_name_plural = _('Leaves / Holidays')
        ordering = ['start_date']
        indexes = [models.Index(fields=['start_date', 'end_date'])]

    def __str__(self):
        who = self.practitioner.name if self.practitioner else _('Clinic holiday')
        return f"{who}: {self.start_date} – {self.end_date}"

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError(_('End date must be on or after the start date.'))


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
        validators=[validate_not_in_past],
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

    class Meta:
        verbose_name = _('Appointment')
        verbose_name_plural = _('Appointments')
        ordering = ['appointment_date', 'appointment_time']
        indexes = [
            models.Index(fields=['patient', 'appointment_date']),
            models.Index(fields=['status', 'appointment_date']),
            models.Index(fields=['practitioner', 'appointment_date']),
        ]

    # Allowed status changes; anything else is rejected by the API.
    TRANSITIONS = {
        'scheduled': {'confirmed', 'completed', 'cancelled', 'no_show'},
        'confirmed': {'completed', 'cancelled', 'no_show'},
        'completed': set(),
        'cancelled': set(),
        'no_show': set(),
        'rescheduled': set(),  # legacy status, kept for old rows
    }
    ACTIVE_STATUSES = ('scheduled', 'confirmed', 'completed')

    def __str__(self):
        name = self.patient.name if self.patient else (self.guest_name or 'Guest')
        return f"{name} — {self.appointment_date} {self.appointment_time}"

    @property
    def status_display(self):
        """Get display name for status."""
        return dict(self.STATUS_CHOICES).get(self.status, self.status)

