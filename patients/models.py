from django.db import models
import uuid
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from clinic.models import Practitioner
from spinalcure.validators import validate_phone_number, validate_not_in_future
from datetime import date, timedelta
from spinalcure.fields import EncryptedCharField, EncryptedTextField, EncryptedEmailField, EncryptedJSONField, phone_digest


class Patient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    """
    Patient information and medical history.
    """
    GENDER_CHOICES = [('M', _('Male')), ('F', _('Female')), ('O', _('Other'))]

    # Personal Info
    patient_id_str = models.CharField(max_length=50, blank=True, null=True, unique=True, verbose_name=_('Patient ID'))
    registration_number = models.CharField(max_length=50, blank=True, null=True, verbose_name=_('Regd. No.'))
    name = EncryptedCharField(
        max_length=255,
        verbose_name=_('Full Name'),
        db_index=True
    )
    phone = EncryptedCharField(
        max_length=255,
        validators=[validate_phone_number],
        verbose_name=_('Phone'),
        db_index=True
    )
    # Keyed hash of `phone` for exact lookups (the encrypted column cannot be queried).
    phone_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    whatsapp_no = EncryptedCharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_('Whatsapp No')
    )
    email = EncryptedEmailField(blank=True, verbose_name=_('Email'), db_index=True)
    address = EncryptedTextField(verbose_name=_('Address'))
    reason_for_visit = EncryptedTextField(blank=True, verbose_name=_('Reason For Visit'))
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    date_of_birth = models.DateField(
        blank=True,
        null=True,
        validators=[validate_not_in_future],
        verbose_name=_('Date of Birth')
    )
    photo = models.ImageField(upload_to='patients/', blank=True, null=True, verbose_name=_('Photo'))

    # Attender Info (optional)
    attender_name = models.CharField(max_length=200, blank=True, verbose_name=_('Attender Name'))
    attender_phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[validate_phone_number],
        verbose_name=_('Attender Phone')
    )
    attender_relation = models.CharField(max_length=100, blank=True, verbose_name=_('Relation'))

    # Medical Info
    chief_complaint = EncryptedTextField(verbose_name=_('Chief Complaint / Problem'))
    medical_history = EncryptedTextField(blank=True, verbose_name=_('Medical History'))
    allergies = EncryptedTextField(blank=True, verbose_name=_('Allergies'))

    # Treatment Plan
    total_sittings = models.PositiveIntegerField(default=0, verbose_name=_('Total Sittings Planned'))

    # Meta
    registered_date = models.DateField(auto_now_add=True, db_index=True)
    handled_by = models.ForeignKey(
        Practitioner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='patients',
        verbose_name=_('Handled By (Doctor)')
    )
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True, verbose_name=_('Additional Notes'))

    class Meta:
        verbose_name = _('Patient')
        verbose_name_plural = _('Patients')
        ordering = ['-registered_date', 'name']
        indexes = [
            models.Index(fields=['phone', 'name']),
            models.Index(fields=['email']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.phone})"

    def save(self, *args, **kwargs):
        self.phone_hash = phone_digest(self.phone)
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and 'phone' in update_fields:
            kwargs['update_fields'] = {*update_fields, 'phone_hash'}
        super().save(*args, **kwargs)

    @classmethod
    def search(cls, qs, query):
        """Filter `qs` by patient ID, reg. no., exact phone or name substring.
        shortcut: names are encrypted, so name matching decrypts all names in Python;
        fine for one clinic (tens of thousands of rows), needs a search index beyond that."""
        q = (query or '').strip().lower()
        if not q:
            return qs
        cond = models.Q(patient_id_str__icontains=q) | models.Q(registration_number__icontains=q)
        digest = phone_digest(q)
        if digest:
            cond |= models.Q(phone_hash=digest)
        name_ids = [pk for pk, name in cls.objects.values_list('pk', 'name') if q in (name or '').lower()]
        return qs.filter(cond | models.Q(pk__in=name_ids))

    @classmethod
    def by_phone(cls, phone):
        digest = phone_digest(phone)
        return cls.objects.filter(phone_hash=digest).first() if digest else None

    @property
    def completed_sittings(self):
        """Number of completed sessions."""
        return self.sessions.filter(session_date__lte=date.today()).count()

    @property
    def remaining_sittings(self):
        """Remaining sittings to be completed."""
        return max(0, self.total_sittings - self.completed_sittings)

    @property
    def progress_percentage(self):
        """Treatment progress as percentage."""
        if self.total_sittings == 0:
            return 0
        return min(100, int((self.completed_sittings / self.total_sittings) * 100))

    @property
    def age(self):
        """Calculate patient age from DOB."""
        if self.date_of_birth:
            today = date.today()
            return today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
        return None

    def clean(self):
        """Validate patient data."""
        if self.email and self.email == self.attender_name:
            raise ValidationError({'email': _('Patient email cannot be same as attender name.')})


class TreatmentPlan(models.Model):
    """
    Represents a specific treatment package or case for a patient.
    E.g. 'Lower Back Pain 2026', 'Frozen Shoulder'.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name='treatment_plans',
        verbose_name=_('Patient'),
        db_index=True,
        db_constraint=False
    )
    name = models.CharField(max_length=200, verbose_name=_('Plan Name'))
    chief_complaint = models.TextField(verbose_name=_('Chief Complaint / Diagnosis'), blank=True)
    total_sittings = models.PositiveIntegerField(verbose_name=_('Total Sittings'), default=0)
    is_active = models.BooleanField(verbose_name=_('Is Active'), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.patient.name} - {self.name}"
        
    @property
    def completed_sittings(self):
        return self.sessions.count()
        
    @property
    def progress_percentage(self):
        if self.total_sittings == 0:
            return 0
        percentage = (self.completed_sittings / self.total_sittings) * 100
        return min(100, int(percentage))

class Session(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    """
    Treatment session records for patients.
    """
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name='sessions',
        verbose_name=_('Patient'),
        db_index=True
    )
    treatment_plan = models.ForeignKey(
        TreatmentPlan,
        on_delete=models.CASCADE,
        related_name='sessions',
        verbose_name=_('Treatment Plan'),
        null=True,
        blank=True
    )
    consulted_by = models.ForeignKey(
        Practitioner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sessions',
        verbose_name=_('Consulted By')
    )
    session_number = models.PositiveIntegerField(verbose_name=_('Session #'))
    session_date = models.DateField(
        verbose_name=_('Session Date'),
        validators=[validate_not_in_future],
        db_index=True
    )
    session_time = models.TimeField(blank=True, null=True, verbose_name=_('Session Time'))

    # Acupuncture Details
    acupoints_used = models.TextField(verbose_name=_('Acupoints / Commanding Points Used'))
    techniques_used = models.TextField(blank=True, verbose_name=_('Techniques Used'))
    duration_minutes = models.PositiveIntegerField(default=30, verbose_name=_('Duration (mins)'))

    # Progress Tracking
    pain_scale = models.PositiveSmallIntegerField(
        default=5, 
        verbose_name=_('Pain Scale (0-10)'),
        help_text=_('0: No pain, 10: Worst possible pain')
    )
    mobility_score = models.PositiveSmallIntegerField(
        default=3, 
        verbose_name=_('Mobility Score (1-5)'),
        help_text=_('1: Immobile, 5: Full mobility')
    )

    # Outcome
    patient_feedback = models.TextField(blank=True, verbose_name=_('Patient Feedback'))
    practitioner_notes = models.TextField(blank=True, verbose_name=_('Practitioner Notes'))
    next_appointment_date = models.DateField(blank=True, null=True, verbose_name=_('Next Appointment'))
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _('Session')
        verbose_name_plural = _('Sessions')
        ordering = ['patient', 'session_number']
        unique_together = ['patient', 'session_number']
        indexes = [
            models.Index(fields=['patient', 'session_date']),
            models.Index(fields=['session_date']),
        ]

    def __str__(self):
        return f"{self.patient.name} — Session #{self.session_number} ({self.session_date})"

    def save(self, *args, **kwargs):
        """Auto-increment session number."""
        if not self.session_number:
            last = Session.objects.filter(patient=self.patient).order_by('-session_number').first()
            self.session_number = (last.session_number + 1) if last else 1
        super().save(*args, **kwargs)

    def clean(self):
        """Validate session data."""
        if self.next_appointment_date and self.next_appointment_date <= self.session_date:
            raise ValidationError({'next_appointment_date': _('Next appointment must be after session date.')})


class PatientReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    """
    Patient reviews and ratings for practitioners.
    """
    RATING_CHOICES = [(1, '1 Star'), (2, '2 Stars'), (3, '3 Stars'), (4, '4 Stars'), (5, '5 Stars')]

    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name=_('Patient'),
        db_index=True
    )
    practitioner = models.ForeignKey(
        Practitioner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviews',
        verbose_name=_('Practitioner')
    )
    rating = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES,
        default=5,
        verbose_name=_('Rating'),
        db_index=True
    )
    review_text = models.TextField(blank=True, verbose_name=_('Review'))
    is_published = models.BooleanField(
        default=False,
        verbose_name=_('Published on Portfolio'),
        db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _('Patient Review')
        verbose_name_plural = _('Patient Reviews')
        ordering = ['-id']
        indexes = [
            models.Index(fields=['is_published', 'rating']),
            models.Index(fields=['practitioner', 'is_published']),
        ]

    def __str__(self):
        return f"{self.patient.name} — {self.rating}★"

    @property
    def star_range(self):
        """Range for displaying star rating."""
        return range(self.rating)

    @property
    def empty_star_range(self):
        """Range for displaying empty stars."""
        return range(5 - self.rating)


class AcupunctureDiagnosis(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.OneToOneField(
        Patient, 
        on_delete=models.CASCADE, 
        related_name='acupuncture_diagnosis',
        verbose_name=_('Patient')
    )
    # Store all the checkboxes and tables as a JSON dictionary
    diagnosis_data = EncryptedJSONField(default=dict, blank=True, verbose_name=_('Diagnosis Data'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Acupuncture Diagnosis')
        verbose_name_plural = _('Acupuncture Diagnoses')

    def __str__(self):
        return f"Diagnosis Sheet for {self.patient.name}"

