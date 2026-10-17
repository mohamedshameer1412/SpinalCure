from django.db import models
# Trigger autoreload to fix FieldDoesNotExist cache issue
import uuid
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from spinalcure.validators import (
    validate_phone_number, validate_gstin, validate_ifsc_code, validate_upi, validate_percentage
)
from .blog_models import BlogPost, BlogTag  # noqa: F401


class ClinicProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    """
    Clinic profile information.
    Only one instance should exist per clinic.
    """
    name = models.CharField(
        max_length=200,
        verbose_name=_('Clinic Name'),
        db_index=True
    )
    tagline = models.CharField(
        max_length=300,
        blank=True,
        verbose_name=_('Tagline')
    )
    logo = models.ImageField(
        upload_to='clinic/',
        blank=True,
        null=True,
        verbose_name=_('Logo')
    )
    about = models.TextField(blank=True, verbose_name=_('About'))
    address = models.TextField(verbose_name=_('Address'))
    phone = models.CharField(
        max_length=100,
        validators=[validate_phone_number],
        verbose_name=_('Phone')
    )
    email = models.EmailField(blank=True, verbose_name=_('Email'))
    website = models.URLField(blank=True, verbose_name=_('Website'))
    facebook = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    twitter = models.URLField(blank=True)
    linkedin = models.URLField(blank=True)
    youtube = models.URLField(blank=True)
    
    @property
    def phone_list(self):
        """Returns a list of phone numbers if multiple are stored."""
        if not self.phone:
            return []
        return [p.strip() for p in self.phone.split(',')]
    
    # Portfolio Dynamic Content
    hero_title = models.CharField(
        max_length=200, 
        blank=True, 
        verbose_name=_('Hero Title'),
        help_text='Main headline on the portfolio page. Leave blank to use default.'
    )
    hero_subtitle = models.TextField(
        blank=True, 
        verbose_name=_('Hero Subtitle'),
        help_text='Paragraph below the headline.'
    )
    hero_image = models.ImageField(
        upload_to='clinic/hero/',
        blank=True,
        null=True,
        verbose_name=_('Hero Image')
    )
    map_iframe_url = models.TextField(
        blank=True,
        verbose_name=_('Google Maps Iframe URL'),
        help_text='Full Google Maps <iframe> HTML code for the contact section.'
    )
    footer_text = models.TextField(
        blank=True,
        verbose_name=_('Footer Text'),
        help_text='Short description to display in the footer above social links.'
    )
    
    working_hours = models.TextField(blank=True, verbose_name=_('Working Hours'))
    established_year = models.PositiveIntegerField(blank=True, null=True)
    registration_number = models.CharField(max_length=100, blank=True)

    # --- ABOUT SECTION ---
    about_label = models.CharField(max_length=100, blank=True, default='Our Legacy', verbose_name=_('About Label'))
    about_title = models.CharField(max_length=200, blank=True, default='A Decade of Healing Hands and Precision.', verbose_name=_('About Title'))
    about_stat1_number = models.CharField(max_length=50, blank=True, default='10+', verbose_name=_('Stat 1 Number'))
    about_stat1_label = models.CharField(max_length=100, blank=True, default='Years Experience', verbose_name=_('Stat 1 Label'))
    about_stat2_number = models.CharField(max_length=50, blank=True, default='15k+', verbose_name=_('Stat 2 Number'))
    about_stat2_label = models.CharField(max_length=100, blank=True, default='Successful Sittings', verbose_name=_('Stat 2 Label'))

    about_quote = models.TextField(blank=True, verbose_name=_('About Quote'))


    # --- SERVICES SECTION (Fixed 3 Slots) ---
    services_label = models.CharField(max_length=100, blank=True, default='Our Expertise', verbose_name=_('Services Label'))
    services_title = models.CharField(max_length=200, blank=True, default='World-Class Therapies', verbose_name=_('Services Title'))
    services_description = models.TextField(blank=True, default='We provide a wide range of specialized services.', verbose_name=_('Services Description'))



    # --- TEAM SECTION ---
    team_label = models.CharField(max_length=100, blank=True, default='The Experts', verbose_name=_('Team Label'))
    team_title = models.CharField(max_length=200, blank=True, default='Meet our Specialists', verbose_name=_('Team Title'))
    team_description = models.TextField(blank=True, default='Highly qualified practitioners dedicated to your recovery journey.', verbose_name=_('Team Description'))

    # --- TESTIMONIALS SECTION ---
    testimonials_label = models.CharField(max_length=100, blank=True, default='Testimonials', verbose_name=_('Testimonials Label'))
    testimonials_title = models.CharField(max_length=200, blank=True, default='Patient Success Stories', verbose_name=_('Testimonials Title'))
    
    # GST & Billing
    gstin = models.CharField(
        max_length=15,
        blank=True,
        validators=[validate_gstin],
        verbose_name=_('GSTIN'),
        help_text='15-digit GST Identification Number (optional)'
    )
    default_tax_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[validate_percentage],
        verbose_name=_('Default Tax %')
    )
    
    # Bank Details
    bank_name = models.CharField(max_length=200, blank=True, verbose_name=_('Bank Name'))
    bank_account = models.CharField(max_length=50, blank=True, verbose_name=_('Account Number'))
    bank_ifsc = models.CharField(
        max_length=20,
        blank=True,
        validators=[validate_ifsc_code],
        verbose_name=_('IFSC Code')
    )
    upi_id = models.CharField(
        max_length=100,
        blank=True,
        validators=[validate_upi],
        verbose_name=_('UPI ID')
    )

    class Meta:
        verbose_name = _('Clinic Profile')
        verbose_name_plural = _('Clinic Profiles')

    def __str__(self):
        return self.name

    def clean(self):
        """Custom validation."""
        if self.established_year:
            from datetime import date
            current_year = date.today().year
            if self.established_year > current_year:
                raise ValidationError({'established_year': _('Year cannot be in the future.')})


class Practitioner(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    """
    Practitioner information (doctors, acupuncturists, etc.)
    """
    GENDER_CHOICES = [('M', _('Male')), ('F', _('Female')), ('O', _('Other'))]

    name = models.CharField(
        max_length=200,
        verbose_name=_('Full Name'),
        db_index=True
    )
    title = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('Title/Designation')
    )
    photo = models.ImageField(
        upload_to='practitioners/',
        blank=True,
        null=True
    )
    gender = models.CharField(
        max_length=1,
        choices=GENDER_CHOICES,
        blank=True
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[validate_phone_number]
    )
    email = models.EmailField(blank=True, db_index=True)
    specialization = models.CharField(
        max_length=300,
        blank=True,
        verbose_name=_('Specialization')
    )
    qualifications = models.TextField(
        blank=True,
        verbose_name=_('Qualifications')
    )
    experience_years = models.PositiveIntegerField(
        default=0,
        verbose_name=_('Years of Experience')
    )
    bio = models.TextField(blank=True, verbose_name=_('Bio'))
    is_chief = models.BooleanField(
        default=False,
        verbose_name=_('Is Chief Doctor'),
        help_text='Chief doctors are displayed in a larger horizontal card.'
    )
    designation_tag = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('Designation Tag'),
        help_text='e.g., Chief Acupuncture Doctor'
    )
    youtube_url = models.URLField(blank=True, verbose_name=_('YouTube URL'))
    twitter = models.URLField(blank=True, verbose_name=_('Twitter URL'))
    instagram = models.URLField(blank=True, verbose_name=_('Instagram URL'))
    facebook = models.URLField(blank=True, verbose_name=_('Facebook URL'))
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Active'),
        db_index=True
    )
    joined_date = models.DateField(blank=True, null=True)

    class Meta:
        verbose_name = _('Practitioner')
        verbose_name_plural = _('Practitioners')
        ordering = ['name']
        indexes = [
            models.Index(fields=['is_active', 'name']),
        ]

    def __str__(self):
        return f"{self.title} {self.name}".strip()

    def clean(self):
        """Custom validation."""
        if self.joined_date:
            from datetime import date
            if self.joined_date > date.today():
                raise ValidationError({'joined_date': _('Joined date cannot be in the future.')})


class ClinicAboutImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    clinic = models.ForeignKey(ClinicProfile, on_delete=models.CASCADE, related_name='about_images')
    image = models.ImageField(upload_to='clinic/about/', verbose_name=_('About Image'))
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = _('About Image')
        verbose_name_plural = _('About Images')


class ClinicService(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    clinic = models.ForeignKey(ClinicProfile, on_delete=models.CASCADE, related_name='services')
    title = models.CharField(max_length=200, verbose_name=_('Service Title'))
    description = models.TextField(verbose_name=_('Service Description'))
    icon = models.CharField(max_length=100, blank=True, verbose_name=_('Icon Name'), help_text='Bootstrap Icon name like bi-heart-pulse')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = _('Service')
        verbose_name_plural = _('Services')

    def __str__(self):
        return self.title

class HeroCarouselImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    clinic = models.ForeignKey(ClinicProfile, on_delete=models.CASCADE, related_name='hero_carousel_images')
    image = models.ImageField(upload_to='clinic/hero_carousel/', verbose_name=_('Hero Image'))
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-created_at']
        verbose_name = _('Hero Carousel Image')
        verbose_name_plural = _('Hero Carousel Images')

    def __str__(self):
        return f"Hero Image for {self.clinic.name} ({self.id})"


class ClinicTestimonial(models.Model):
    """
    Curated testimonials displayed on the public portfolio.
    Managed by admins — separate from PatientReview (which is patient-submitted).
    """
    SOURCE_CHOICES = [
        ('google', _('Google Review')),
        ('internal', _('Internal / Direct')),
        ('walk_in', _('Walk-in Patient')),
        ('event', _('Event Attendee')),
        ('course', _('Course Student')),
        ('social', _('Social Media')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    clinic = models.ForeignKey(
        ClinicProfile,
        on_delete=models.CASCADE,
        related_name='testimonials',
        verbose_name=_('Clinic')
    )
    patient_name = models.CharField(max_length=200, verbose_name=_('Patient / Client Name'))
    patient_designation = models.CharField(
        max_length=200, blank=True,
        verbose_name=_('Designation / Location'),
        help_text='e.g., "Teacher, Chennai" or "Software Engineer, Bangalore"'
    )
    photo = models.ImageField(
        upload_to='testimonials/', blank=True, null=True,
        verbose_name=_('Photo')
    )
    rating = models.PositiveSmallIntegerField(
        default=5,
        choices=[(i, f'{i} Star{"s" if i > 1 else ""}') for i in range(1, 6)],
        verbose_name=_('Rating')
    )
    review_text = models.TextField(verbose_name=_('Testimonial Text'))
    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default='internal',
        verbose_name=_('Source')
    )
    is_published = models.BooleanField(default=False, verbose_name=_('Published'), db_index=True)
    display_order = models.PositiveIntegerField(default=0, verbose_name=_('Display Order'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Testimonial')
        verbose_name_plural = _('Testimonials')
        ordering = ['display_order', '-created_at']

    def __str__(self):
        return f"{self.patient_name} — {self.rating}★"


class AuditLog(models.Model):
    """
    Tracks all Create, Update, Delete actions performed by staff and admin users.
    Used for accountability, compliance, and monitoring staff activity.
    """
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'

    ACTION_CHOICES = [
        (ACTION_CREATE, _('Create')),
        (ACTION_UPDATE, _('Update')),
        (ACTION_DELETE, _('Delete')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs',
        verbose_name=_('User')
    )
    action = models.CharField(
        max_length=10,
        choices=ACTION_CHOICES,
        db_index=True,
        verbose_name=_('Action')
    )
    model_name = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name=_('Model / Module'),
        help_text=_('e.g. Patient, Payment, Session, Course, Event, Appointment')
    )
    object_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('Record ID')
    )
    object_repr = models.CharField(
        max_length=300,
        blank=True,
        verbose_name=_('Record Description'),
        help_text=_('Human-readable string of the affected record')
    )
    changes = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_('Changes'),
        help_text=_('JSON of changed fields (human-readable): {"field": {"old": "...", "new": "..."}}')
    )
    raw_changes = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_('Raw Changes'),
        help_text=_('JSON of actual database field changes for programmatic reverting')
    )
    snapshot = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_('Snapshot'),
        help_text=_('Complete serialized JSON representation of the object before deletion')
    )
    reverted = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_('Reverted'),
        help_text=_('Whether this action has been reverted')
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_('IP Address')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name=_('Timestamp')
    )

    class Meta:
        verbose_name = _('Audit Log')
        verbose_name_plural = _('Audit Logs')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'action']),
            models.Index(fields=['model_name', 'action']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        user_str = self.user.get_full_name() if self.user else 'Unknown'
        return f"[{self.get_action_display()}] {self.model_name}: {self.object_repr} by {user_str}"
