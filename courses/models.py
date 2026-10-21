import secrets
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from spinalcure.pricing import DiscountMixin, original_price_field


class Course(DiscountMixin, models.Model):
    """A training course offered by the clinic."""
    PLATFORM_ONLINE = 'online'
    PLATFORM_OFFLINE = 'offline'
    PLATFORM_HYBRID = 'hybrid'
    PLATFORM_CHOICES = [
        (PLATFORM_ONLINE, 'Online'),
        (PLATFORM_OFFLINE, 'Offline (In-person)'),
        (PLATFORM_HYBRID, 'Hybrid (Online + Offline)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300, verbose_name=_('Title'))
    slug = models.SlugField(max_length=320, unique=True, blank=True, verbose_name=_('Slug'))
    short_description = models.CharField(
        max_length=500, verbose_name=_('Short Description'),
        help_text=_('Displayed on the portfolio card.')
    )
    description = models.TextField(verbose_name=_('Full Description'))
    outcomes = models.TextField(
        verbose_name=_('Learning Outcomes'),
        help_text=_('One outcome per line. Displayed as a bullet list.')
    )
    course_content = models.TextField(
        verbose_name=_('Course Content / Syllabus'),
        help_text=_('Detailed module/topic list. One topic per line or use markdown-style numbering.')
    )
    platform = models.CharField(
        max_length=10, choices=PLATFORM_CHOICES, default=PLATFORM_OFFLINE,
        verbose_name=_('Platform')
    )
    fees = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name=_('Course Fees (₹)')
    )
    original_fees = original_price_field()
    duration = models.CharField(
        max_length=100, blank=True, verbose_name=_('Duration'),
        help_text=_('e.g. 3 months, 12 weeks')
    )
    image = models.ImageField(
        upload_to='courses/', blank=True, null=True, verbose_name=_('Cover Image')
    )
    is_published = models.BooleanField(
        default=False, db_index=True, verbose_name=_('Published')
    )
    clinic = models.ForeignKey(
        'clinic.ClinicProfile',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='courses',
        verbose_name=_('Clinic')
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Course')
        verbose_name_plural = _('Courses')
        ordering = ['-created_at']

    def clean(self):
        self.clean_discount()

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base = slugify(self.title)
            slug = base
            n = 1
            while Course.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def active_batch(self):
        return self.batches.filter(is_active=True).first()

    @property
    def published_feedback_count(self):
        return self.feedback.filter(is_published=True).count()

    @property
    def avg_rating(self):
        feedbacks = self.feedback.filter(is_published=True)
        if not feedbacks.exists():
            return 0
        return round(sum(f.rating for f in feedbacks) / feedbacks.count(), 1)

    def get_outcomes_list(self):
        return [line.strip() for line in self.outcomes.splitlines() if line.strip()]

    def get_content_list(self):
        return [line.strip() for line in self.course_content.splitlines() if line.strip()]


class CourseBatch(models.Model):
    """A specific run/intake of a course."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name='batches', verbose_name=_('Course')
    )
    name = models.CharField(
        max_length=200, verbose_name=_('Batch Name'),
        help_text=_('e.g. "2025 Batch", "Batch 3 — June 2024"')
    )
    start_date = models.DateField(verbose_name=_('Start Date'))
    end_date = models.DateField(null=True, blank=True, verbose_name=_('End Date'))
    schedule_details = models.TextField(
        blank=True, verbose_name=_('Schedule Details'),
        help_text=_('e.g. Every Saturday 10AM–1PM')
    )
    max_participants = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_('Max Seats')
    )
    is_active = models.BooleanField(
        default=False, db_index=True,
        verbose_name=_('Current / Active Batch'),
        help_text=_('The active batch is open for new registrations.')
    )
    feedback_enabled = models.BooleanField(
        default=False, verbose_name=_('Feedback Form Enabled'),
        help_text=_('Enable after the batch ends so alumni can submit reviews.')
    )
    is_published = models.BooleanField(default=True, verbose_name=_('Published'))

    class Meta:
        verbose_name = _('Course Batch')
        verbose_name_plural = _('Course Batches')
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.course.title} — {self.name}"

    @property
    def is_completed(self):
        """Batch is completed if end_date is in the past."""
        if self.end_date:
            return self.end_date < timezone.localdate()
        return not self.is_active

    @property
    def registration_count(self):
        return self.registrations.filter(status='confirmed').count()

    @property
    def is_full(self):
        return self.max_participants is not None and self.registration_count >= self.max_participants


class CourseRegistration(models.Model):
    """A student's registration for a specific course batch."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(
        CourseBatch, on_delete=models.CASCADE,
        related_name='registrations', verbose_name=_('Batch')
    )
    name = models.CharField(max_length=200, verbose_name=_('Full Name'))
    phone = models.CharField(max_length=20, verbose_name=_('Phone'))
    email = models.EmailField(blank=True, verbose_name=_('Email'))
    notes = models.TextField(blank=True, verbose_name=_('Notes / Questions'))
    registered_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Registered At'))
    STATUS_CHOICES = [('confirmed', _('Confirmed')), ('waitlisted', _('Waitlisted')), ('cancelled', _('Cancelled'))]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='confirmed', db_index=True)
    phone_key = models.CharField(max_length=15, blank=True, db_index=True, editable=False)
    access_token = models.CharField(max_length=43, unique=True, editable=False, default=secrets.token_urlsafe)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    promoted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('Course Registration')
        verbose_name_plural = _('Course Registrations')
        ordering = ['-registered_at']

    def __str__(self):
        return f"{self.name} — {self.batch}"


class CourseFeedback(models.Model):
    """Feedback from a student who completed a past batch.
    Linked to the Course (shows across all batches as social proof)
    but gated by a specific CourseRegistration (past/completed batches only).
    """
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE,
        related_name='feedback', verbose_name=_('Course')
    )
    batch = models.ForeignKey(
        CourseBatch, on_delete=models.CASCADE,
        related_name='feedback', verbose_name=_('Batch'),
        help_text=_('Which batch the reviewer attended.')
    )
    registration = models.OneToOneField(
        CourseRegistration, on_delete=models.CASCADE,
        related_name='feedback',
        verbose_name=_('Registration'),
        help_text=_('One feedback per student per course.')
    )
    reviewer_name = models.CharField(max_length=200, verbose_name=_('Name'))
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES, verbose_name=_('Rating'))
    comment = models.TextField(verbose_name=_('Comment'))
    is_published = models.BooleanField(
        default=False, db_index=True, verbose_name=_('Published')
    )
    submitted_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Submitted At'))

    class Meta:
        verbose_name = _('Course Feedback')
        verbose_name_plural = _('Course Feedbacks')
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.reviewer_name} — {self.course.title} ({self.rating}★)"
