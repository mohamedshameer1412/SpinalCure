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

    class Meta:
        verbose_name = _('Doctor Availability')
        verbose_name_plural = _('Doctor Availabilities')
        unique_together = ['practitioner', 'day_of_week']
        ordering = ['practitioner', 'day_of_week']
        indexes = [
            models.Index(fields=['day_of_week', 'is_available']),
        ]

    def __str__(self):
        return f"{self.practitioner.name} — {self.get_day_of_week_display()}"

    def clean(self):
        """Validate time range."""
        validate_time_range(self.start_time, self.end_time)


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

    def __str__(self):
        return f"{self.patient.name} — {self.appointment_date} {self.appointment_time}"

    def clean(self):
        """Validate appointment data."""
        if self.practitioner and self.appointment_date:
            from datetime import date, datetime, time
            # Check day of week
            day_of_week = self.appointment_date.weekday()
            
            # Check if practitioner is available on this day
            availability = DoctorAvailability.objects.filter(
                practitioner=self.practitioner,
                day_of_week=day_of_week,
                is_available=True
            ).first()
            
            if not availability:
                raise ValidationError(
                    {'practitioner': _('Practitioner is not available on this day.')}
                )
            
            # Note: Specific shift validation (10am-1pm, etc.) is handled by the slot API.
            # We allow valid appointment saving if the day matches availability.

    @property
    def status_display(self):
        """Get display name for status."""
        return dict(self.STATUS_CHOICES).get(self.status, self.status)

