from django.db import models
# Trigger autoreload to fix FieldDoesNotExist cache issue
import uuid
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from spinalcure.languages import NATIVE_CHOICES
from spinalcure.uploads import RandomName
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

    @property
    def map_embed_src(self):
        """The Google Maps embed URL from the pasted <iframe> code (or plain URL), or '' if it is anything else.
        The page renders its own iframe from this; the pasted HTML itself is never output."""
        import re
        from urllib.parse import urlsplit
        raw = (self.map_iframe_url or '').strip()
        m = re.search(r'src\s*=\s*["\']([^"\']+)["\']', raw, re.I)
        url = (m.group(1) if m else raw).replace('&amp;', '&')
        parts = urlsplit(url)
        if parts.scheme == 'https' and parts.hostname in ('www.google.com', 'maps.google.com', 'google.com') \
                and (parts.path.startswith('/maps/embed') or 'output=embed' in parts.query):
            return url
        return ''

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


class ProblemCategory(models.Model):
    """Health problem a testimonial or video relates to; drives the public search dropdown."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, verbose_name=_('Problem'))
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    keywords = models.CharField(
        max_length=300, blank=True, verbose_name=_('Search keywords'),
        help_text=_('Comma-separated extra words that should match this problem, e.g. "disc, herniated".')
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = _('Problem Category')
        verbose_name_plural = _('Problem Categories')

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


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
    problem = models.ForeignKey(
        ProblemCategory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='testimonials', verbose_name=_('Problem treated')
    )
    owner_reply = models.TextField(blank=True, verbose_name=_('Clinic reply'))
    source_url = models.URLField(blank=True, verbose_name=_('Source link'))
    posted_label = models.CharField(
        max_length=50, blank=True, verbose_name=_('Posted'),
        help_text=_('Free text shown on the card, e.g. "2 months ago".')
    )
    is_published = models.BooleanField(default=False, verbose_name=_('Published'), db_index=True)
    display_order = models.PositiveIntegerField(default=0, verbose_name=_('Display Order'))
    created_at = models.DateTimeField(auto_now_add=True)

    # Provenance, consent and moderation. Public submissions need the writer's consent before staff can publish
    # them, and the writer can withdraw it with the private link shown after submitting.
    SUBMITTED_VIA_CHOICES = [('staff', _('Added by staff')), ('public_form', _('Website form'))]
    MODERATION_CHOICES = [('pending', _('Pending review')), ('approved', _('Approved')), ('rejected', _('Rejected')),
                          ('spam', _('Spam')), ('withdrawn', _('Withdrawn by author'))]
    submitted_via = models.CharField(max_length=12, choices=SUBMITTED_VIA_CHOICES, default='staff')
    moderation_status = models.CharField(max_length=10, choices=MODERATION_CHOICES, default='approved', db_index=True)
    consent_to_publish = models.BooleanField(default=False, verbose_name=_('Author agreed to publication'))
    consent_at = models.DateTimeField(null=True, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdraw_token = models.CharField(max_length=43, blank=True, db_index=True, editable=False)
    content_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _('Testimonial')
        verbose_name_plural = _('Testimonials')
        ordering = ['display_order', '-created_at']

    def __str__(self):
        return f"{self.patient_name} — {self.rating}★"

    def save(self, *args, **kwargs):
        if self.moderation_status in ('withdrawn', 'spam', 'rejected'):
            self.is_published = False      # never public, whatever path saved it
        super().save(*args, **kwargs)

    @property
    def can_publish(self):
        if self.moderation_status in ('withdrawn', 'spam', 'rejected'):
            return False
        return self.submitted_via != 'public_form' or self.consent_to_publish


class TestimonialModeration(models.Model):
    """Append-only history of what happened to a testimonial (submitted, approved, published, withdrawn ...).
    Kept when the testimonial is deleted; no database constraint so it also works on legacy char(32) tables."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    testimonial = models.ForeignKey(ClinicTestimonial, on_delete=models.SET_NULL, null=True, blank=True,
                                    db_constraint=False, related_name='moderation_history')
    action = models.CharField(max_length=20)
    actor = models.CharField(max_length=150, blank=True, help_text=_('Username, or "author" / "system".'))
    note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action} by {self.actor or "system"}'


class TestimonialVideo(models.Model):
    """Patient story shared as a YouTube Short/video or Instagram reel; embedded, never downloaded."""
    PLATFORM_CHOICES = [('youtube', 'YouTube'), ('instagram', 'Instagram')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200, verbose_name=_('Title'))
    patient_name = models.CharField(max_length=200, blank=True, verbose_name=_('Patient name'))
    url = models.URLField(verbose_name=_('Video / Reel / Short link'))
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES, blank=True, editable=False)
    video_id = models.CharField(max_length=64, blank=True, editable=False)
    problem = models.ForeignKey(
        ProblemCategory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='videos', verbose_name=_('Problem treated')
    )
    description = models.TextField(blank=True, verbose_name=_('Short description'))
    is_published = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    # Media library: language, transcript (accessibility and search), consent, and a thumbnail with a focal point
    # so one image crops well to 16:9, 4:5 and 9:16.
    CONSENT_CHOICES = [('unrecorded', _('Not recorded')), ('obtained', _('Consent on file')), ('withdrawn', _('Withdrawn'))]
    LAYOUT_CHOICES = [('auto', _('Automatic')), ('16:9', '16:9'), ('4:5', '4:5'), ('9:16', '9:16')]
    THUMB_SOURCE_CHOICES = [('platform', _('Platform thumbnail')), ('upload', _('Uploaded image')),
                            ('frame1', _('Video frame 1')), ('frame2', _('Video frame 2')), ('frame3', _('Video frame 3'))]
    language = models.CharField(max_length=5, choices=NATIVE_CHOICES, default='en', verbose_name=_('Language'))
    transcript = models.TextField(blank=True, verbose_name=_('Transcript'))
    consent_status = models.CharField(max_length=10, choices=CONSENT_CHOICES, default='unrecorded', db_index=True,
                                      verbose_name=_('Patient consent'))
    consent_note = models.CharField(max_length=300, blank=True, verbose_name=_('Where consent is recorded'),
                                    help_text=_('e.g. "Signed media consent form, file 2026/14". Never upload the form itself here.'))
    consent_date = models.DateField(null=True, blank=True, verbose_name=_('Consent date'))
    thumbnail = models.ImageField(upload_to=RandomName('stories'), blank=True, null=True, verbose_name=_('Thumbnail'))
    thumbnail_source = models.CharField(max_length=10, choices=THUMB_SOURCE_CHOICES, default='platform')
    focal_x = models.PositiveSmallIntegerField(default=50, validators=[MaxValueValidator(100)])
    focal_y = models.PositiveSmallIntegerField(default=50, validators=[MaxValueValidator(100)])
    layout = models.CharField(max_length=5, choices=LAYOUT_CHOICES, default='auto', verbose_name=_('Card layout'))
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        verbose_name = _('Testimonial Video')
        verbose_name_plural = _('Testimonial Videos')
        ordering = ['display_order', '-created_at']

    def __str__(self):
        return self.title

    @staticmethod
    def parse_url(url):
        """Return (platform, id) for a YouTube/Shorts/Instagram reel link, or ('', '')."""
        import re
        m = re.search(r'(?:youtube\.com/(?:shorts/|watch\?v=|embed/)|youtu\.be/)([\w-]{6,20})', url)
        if m:
            return 'youtube', m.group(1)
        m = re.search(r'instagram\.com/(?:[\w.]+/)?(?:reels?|p|tv)/([\w-]+)', url)
        if m:
            return 'instagram', m.group(1)
        return '', ''

    def clean(self):
        self.platform, self.video_id = self.parse_url(self.url or '')
        if not self.platform:
            raise ValidationError({'url': _('Enter a YouTube, YouTube Shorts or Instagram reel link.')})

    def save(self, *args, **kwargs):
        self.platform, self.video_id = self.parse_url(self.url or '')
        if self.consent_status == 'withdrawn':
            self.is_published = False
        super().save(*args, **kwargs)

    @property
    def embed_url(self):
        if self.platform == 'youtube':
            return f'https://www.youtube-nocookie.com/embed/{self.video_id}?rel=0'
        if self.platform == 'instagram':
            return f'https://www.instagram.com/reel/{self.video_id}/embed'
        return ''

    @property
    def is_vertical(self):
        return self.platform == 'instagram' or '/shorts/' in self.url

    @property
    def thumbnail_url(self):
        if self.thumbnail:
            try:
                return self.thumbnail.url
            except ValueError:
                pass
        if self.platform == 'youtube':
            return f'https://i.ytimg.com/vi/{self.video_id}/hqdefault.jpg'
        return ''

    @property
    def aspect(self):
        if self.layout != 'auto':
            return self.layout
        return '9:16' if self.is_vertical else '16:9'

    @property
    def can_publish(self):
        return self.consent_status == 'obtained'


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


class Translation(models.Model):
    """One translated text unit (model + object + field + language). English lives on the model itself.
    A person's words (edited/final) are never overwritten by a machine; see clinic/content_i18n.py."""
    STATUS_CHOICES = [('auto', _('Auto-translated')), ('edited', _('Edited by staff')), ('final', _('Reviewed'))]

    model_label = models.CharField(max_length=60)
    object_id = models.CharField(max_length=64)
    field = models.CharField(max_length=60)
    lang = models.CharField(max_length=5, db_index=True)
    value = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='auto')
    method = models.CharField(max_length=40, blank=True, help_text='manual, or machine:<provider>')
    source_hash = models.CharField(max_length=16, blank=True, help_text='Hash of the English text this was made from.')
    updated_by = models.CharField(max_length=150, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('model_label', 'object_id', 'field', 'lang')]
        indexes = [models.Index(fields=['lang', 'model_label'])]

    def __str__(self):
        return f'{self.model_label}:{self.field} [{self.lang}]'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from django.core.cache import cache
        cache.delete(f'content_tr_{self.lang}')

    def delete(self, *args, **kwargs):
        from django.core.cache import cache
        cache.delete(f'content_tr_{self.lang}')
        return super().delete(*args, **kwargs)
