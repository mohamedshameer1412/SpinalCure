from django.db import models
# Trigger autoreload to fix FieldDoesNotExist cache issue
import uuid
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from spinalcure.languages import NATIVE_CHOICES
from spinalcure.uploads import RandomName, SafeImageField, SafeVideoField, validate_safe_video
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
    logo = SafeImageField(
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
    google_review_url = models.URLField(
        blank=True, verbose_name=_('Google review link'),
        help_text=_('From Google Business Profile: "Ask for reviews". Patients are sent here after their treatment.'))
    
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
    hero_image = SafeImageField(
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
    photo = SafeImageField(
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
    image = SafeImageField(upload_to='clinic/about/', verbose_name=_('About Image'))
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
    image = SafeImageField(upload_to='clinic/hero_carousel/', verbose_name=_('Hero Image'))
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-created_at']
        verbose_name = _('Hero Carousel Image')
        verbose_name_plural = _('Hero Carousel Images')

    def __str__(self):
        return f"Hero Image for {self.clinic.name} ({self.id})"


# Hues for story cards (Tailwind safelists the classes, see tailwind.config.js). One per problem, stable.
STORY_HUES = ('emerald', 'sky', 'violet', 'amber', 'rose', 'teal', 'indigo', 'orange')


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

    @property
    def hue(self):
        return STORY_HUES[self.pk.int % len(STORY_HUES)] if self.pk else STORY_HUES[0]

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class FAQ(models.Model):
    """A patient question answered by the clinic: the public FAQ page (and its FAQPage structured data)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.CharField(max_length=300, verbose_name=_('Question'))
    answer = models.TextField(verbose_name=_('Answer'))
    problem = models.ForeignKey(ProblemCategory, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='faqs', verbose_name=_('Problem'))
    order = models.PositiveIntegerField(default=0, verbose_name=_('Display order'))
    is_published = models.BooleanField(
        default=False, db_index=True, verbose_name=_('Published'),
        help_text=_('Publish only after the doctor has checked the answer.'))
    reviewed_by = models.CharField(max_length=120, blank=True, verbose_name=_('Checked by'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'question']
        verbose_name = _('FAQ')
        verbose_name_plural = _('FAQs')

    def __str__(self):
        return self.question


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
    photo = SafeImageField(
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
    thumbnail = SafeImageField(upload_to=RandomName('stories'), blank=True, null=True, verbose_name=_('Thumbnail'))
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
    def is_short(self):
        """True when this is a YouTube Short - Shorts cannot be embedded (Error 153)."""
        return self.platform == 'youtube' and '/shorts/' in self.url

    @property
    def embed_url(self):
        """Embed URL for iframes. Returns '' for YouTube Shorts (use direct_url instead)."""
        if self.platform == 'youtube' and not self.is_short:
            return f'https://www.youtube-nocookie.com/embed/{self.video_id}?rel=0'
        if self.platform == 'instagram':
            return f'https://www.instagram.com/reel/{self.video_id}/embed'
        return ''

    @property
    def direct_url(self):
        """URL to open on YouTube directly - used for Shorts that cannot be embedded (Error 153)."""
        if self.is_short:
            return f'https://www.youtube.com/shorts/{self.video_id}'
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

    @property
    def cover_variant(self):
        """0-2, stable per video: which branded cover a video without a thumbnail gets."""
        return self.pk.int % 3 if self.pk else 0

    # Lists set `slot` (position on the page, see stories.with_slots) so neighbouring cards never share a design.
    @property
    def _slot(self):
        slot = getattr(self, 'slot', None)
        return slot if slot is not None else (self.pk.int if self.pk else 0)

    @property
    def card_variant(self):
        """0-3: which of the four cover designs this card uses."""
        return (self._slot + self._slot // 4) % 4      # shifts every row, so columns don't repeat either

    @property
    def hue(self):
        """The problem's colour; untagged stories take one from their position, offset from the design."""
        return self.problem.hue if self.problem_id else STORY_HUES[(self._slot * 3 + 1) % len(STORY_HUES)]


class FeaturedPatient(models.Model):
    """A well-known patient the clinic is permitted to name. Shown as information, never as an advert."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, verbose_name=_('Name'))
    profession = models.CharField(max_length=120, blank=True, verbose_name=_('Known as'),
                                  help_text=_('e.g. "Actor", "Cricketer".'))
    photo = SafeImageField(upload_to=RandomName('featured'), verbose_name=_('Photo'))
    note = models.CharField(max_length=300, blank=True, verbose_name=_('Short note'),
                            help_text=_('Optional, factual and brief. No treatment claims.'))
    consent_confirmed = models.BooleanField(
        default=False, verbose_name=_('Permission to feature is on file'),
        help_text=_('Tick only when the patient (or their team) has agreed in writing to be named on the website.'))
    order = models.PositiveIntegerField(default=0, verbose_name=_('Display order'))
    is_published = models.BooleanField(default=False, db_index=True, verbose_name=_('Published'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = _('Featured patient')
        verbose_name_plural = _('Featured patients')

    def __str__(self):
        return self.name

    def clean(self):
        if self.is_published and not self.consent_confirmed:
            raise ValidationError({'is_published': _('Confirm the permission is on file before publishing.')})


validate_video_file = validate_safe_video          # name kept: migration 0014 refers to it


class GalleryItem(models.Model):
    """A photo or video on the public gallery. Featured items (e.g. a well-known patient's visit) get a spotlight."""
    KIND_CHOICES = [('photo', _('Photo')), ('video', _('Video'))]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=5, choices=KIND_CHOICES, default='photo', verbose_name=_('Type'))
    title = models.CharField(max_length=200, verbose_name=_('Title'))
    caption = models.TextField(blank=True, verbose_name=_('Caption'))
    image = SafeImageField(upload_to=RandomName('gallery'), blank=True, null=True, verbose_name=_('Photo / cover image'))
    video_file = SafeVideoField(upload_to=RandomName('gallery/videos'), blank=True, null=True,
                                  verbose_name=_('Video file'))
    video_url = models.URLField(blank=True, verbose_name=_('or YouTube / Instagram link'))
    is_featured = models.BooleanField(default=False, db_index=True, verbose_name=_('Featured'))
    featured_label = models.CharField(max_length=80, blank=True, verbose_name=_('Featured label'),
                                      help_text=_('Shown on the spotlight, e.g. "Featured patient".'))
    order = models.PositiveIntegerField(default=0, verbose_name=_('Display order'))
    is_published = models.BooleanField(default=True, db_index=True, verbose_name=_('Published'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_featured', 'order', '-created_at']
        verbose_name = _('Gallery item')
        verbose_name_plural = _('Gallery')

    def __str__(self):
        return self.title

    def clean(self):
        if self.kind == 'photo' and not self.image:
            raise ValidationError({'image': _('Choose a photo.')})
        if self.kind == 'video':
            if not (self.video_file or self.video_url):
                raise ValidationError({'video_file': _('Upload a video or paste a YouTube / Instagram link.')})
            if self.video_url and not TestimonialVideo.parse_url(self.video_url)[0]:
                raise ValidationError({'video_url': _('Enter a YouTube, YouTube Shorts or Instagram reel link.')})

    @property
    def is_short(self):
        """True when this is a YouTube Short - Shorts cannot be embedded (Error 153)."""
        return '/shorts/' in (self.video_url or '')

    @property
    def embed_url(self):
        """Embed URL for iframes. Returns '' for YouTube Shorts (use direct_url instead)."""
        platform, vid = TestimonialVideo.parse_url(self.video_url or '')
        if platform == 'youtube' and not self.is_short:
            return f'https://www.youtube-nocookie.com/embed/{vid}?rel=0&autoplay=1'
        if platform == 'instagram':
            return f'https://www.instagram.com/reel/{vid}/embed'
        return ''

    @property
    def direct_url(self):
        """URL to open on YouTube directly - used for Shorts that cannot be embedded (Error 153)."""
        if self.is_short:
            platform, vid = TestimonialVideo.parse_url(self.video_url or '')
            if vid:
                return f'https://www.youtube.com/shorts/{vid}'
        return ''

    @property
    def is_vertical(self):
        return 'instagram.com' in (self.video_url or '') or '/shorts/' in (self.video_url or '')


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
