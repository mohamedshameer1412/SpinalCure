import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from django.utils import timezone


class BlogTag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True, verbose_name=_('Tag Name'))
    slug = models.SlugField(max_length=60, unique=True, blank=True)

    class Meta:
        verbose_name = _('Blog Tag')
        verbose_name_plural = _('Blog Tags')
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class BlogPost(models.Model):
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('published', _('Published')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300, verbose_name=_('Title'))
    slug = models.SlugField(max_length=320, unique=True, blank=True, db_index=True)
    excerpt = models.TextField(
        max_length=500,
        blank=True,
        verbose_name=_('Excerpt'),
        help_text=_('Short summary shown on the blog listing card (max 500 chars).')
    )
    content = models.TextField(verbose_name=_('Content'))
    cover_image = models.ImageField(
        upload_to='blog/covers/',
        blank=True,
        null=True,
        verbose_name=_('Cover Image'),
        help_text=_('Recommended size: 1200 x 630 px')
    )

    # Authorship
    author = models.ForeignKey(
        'clinic.Practitioner',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blog_posts',
        verbose_name=_('Author')
    )
    author_name_override = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_('Author Name Override'),
        help_text=_('Use this if the author is not a practitioner in the system.')
    )

    # Categorisation
    tags = models.ManyToManyField(BlogTag, blank=True, related_name='posts', verbose_name=_('Tags'))

    # Publishing
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Published At'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # SEO
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        verbose_name=_('Meta Description'),
        help_text=_('Shown in Google search results (max 160 chars).')
    )

    # Read time (auto-computed)
    read_time_minutes = models.PositiveIntegerField(default=0, verbose_name=_('Read Time (minutes)'))

    class Meta:
        verbose_name = _('Blog Post')
        verbose_name_plural = _('Blog Posts')
        ordering = ['-published_at', '-created_at']
        indexes = [
            models.Index(fields=['status', '-published_at']),
        ]

    def __str__(self):
        return self.title

    @property
    def display_author(self):
        if self.author:
            return str(self.author)
        return self.author_name_override or 'SpinalCure Team'

    @property
    def is_published(self):
        return self.status == 'published'

    def save(self, *args, **kwargs):
        # 1. Auto-slug
        if not self.slug:
            base = slugify(self.title)[:280]
            self.slug = base
            counter = 1
            while BlogPost.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{base}-{counter}"
                counter += 1

        # 2. Auto-publish timestamp
        if self.status == 'published' and not self.published_at:
            self.published_at = timezone.now()

        # 3. Content Clean-up for Read Time, Excerpt, and SEO (Strip HTML)
        import re
        clean_text = re.sub(r'<[^>]+>', ' ', self.content)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        word_count = len(clean_text.split())

        # 4. Auto read-time (~200 words per minute)
        self.read_time_minutes = max(1, round(word_count / 200))

        # 5. Auto-generate Excerpt (if empty)
        if not self.excerpt and clean_text:
            self.excerpt = clean_text[:497] + '...' if len(clean_text) > 500 else clean_text

        # 6. Auto-generate Meta Description (if empty)
        if not self.meta_description and clean_text:
            # Meta descriptions should be around 155-160 chars
            self.meta_description = clean_text[:157] + '...' if len(clean_text) > 160 else clean_text

        super().save(*args, **kwargs)
