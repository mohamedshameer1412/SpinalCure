"""Patient stories: public review intake (spam, duplicates, consent, withdrawal), moderation history, and the
thumbnail pipeline for story videos (frame import, focal-point crops, WebP/AVIF renditions).

Nothing here creates patient media: thumbnails are either uploaded by staff or taken from the clinic's own
published YouTube video."""
import hashlib
import io
import logging
import re
import secrets
import urllib.request
from datetime import timedelta

from django.core import signing
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext

from .models import ClinicProfile, ClinicTestimonial, ProblemCategory, TestimonialModeration

logger = logging.getLogger(__name__)

FORM_SALT = 'review-form'
MIN_FILL_SECONDS = 3            # bots post the form instantly
MAX_LINKS = 1
DUPLICATE_WINDOW_DAYS = 90


class ReviewRejected(Exception):
    def __init__(self, message, status=400, silent=False):
        super().__init__(message)
        self.message, self.status, self.silent = message, status, silent


def log(testimonial, action, actor='', note=''):
    TestimonialModeration.objects.create(testimonial=testimonial, action=action, actor=str(actor)[:150], note=note[:300])


# ── public intake ────────────────────────────────────────────────────────────────────────────────────────

def form_token():
    """Signed render time, sent back with the form: a submission that arrives too fast is a bot."""
    return signing.dumps(int(timezone.now().timestamp()), salt=FORM_SALT)


def _fill_seconds(token):
    try:
        started = signing.loads(token or '', salt=FORM_SALT, max_age=6 * 3600)
    except signing.BadSignature:
        return None
    return timezone.now().timestamp() - started


def _normalise(text):
    return re.sub(r'\W+', ' ', text.lower()).strip()


def content_hash(name, text):
    return hashlib.sha256(f'{_normalise(name)}|{_normalise(text)}'.encode()).hexdigest()


def submit_public_review(data):
    """Validate and store a website review as pending. Returns the testimonial. Raises ReviewRejected; when
    `silent` is set the caller answers as if it succeeded (honeypot / timing trap), so bots learn nothing."""
    if str(data.get('website', '')).strip():
        raise ReviewRejected('honeypot', silent=True)
    elapsed = _fill_seconds(str(data.get('form_token', '')))
    if elapsed is None or elapsed < MIN_FILL_SECONDS:
        raise ReviewRejected('timing', silent=True)
    name = str(data.get('name', '')).strip()[:120]
    text = str(data.get('review', '')).strip()[:2000]
    place = str(data.get('place', '')).strip()[:120]
    try:
        rating = int(data.get('rating'))
    except (TypeError, ValueError):
        rating = 0
    if len(name) < 2 or len(text) < 10:
        raise ReviewRejected(gettext('Please enter your name and a few words about your experience.'))
    if rating not in range(1, 6):
        raise ReviewRejected(gettext('Invalid rating value.'))
    if data.get('consent') is not True:
        raise ReviewRejected(gettext('Please confirm that we may publish your review.'))
    if len(re.findall(r'https?://|www\.', text, re.I)) > MAX_LINKS:
        raise ReviewRejected(gettext('Please remove the links from your review.'))
    clinic = ClinicProfile.objects.first()
    if clinic is None:
        raise ReviewRejected(gettext('An error occurred. Please try again.'), status=503)
    digest = content_hash(name, text)
    since = timezone.now() - timedelta(days=DUPLICATE_WINDOW_DAYS)
    if ClinicTestimonial.objects.filter(content_hash=digest, created_at__gte=since).exists():
        raise ReviewRejected(gettext('We have already received this review. Thank you!'), status=409)
    with transaction.atomic():
        t = ClinicTestimonial.objects.create(
            clinic=clinic, patient_name=name, patient_designation=place, rating=rating, review_text=text,
            problem=ProblemCategory.objects.filter(slug=str(data.get('problem', ''))[:120], is_active=True).first(),
            source='internal', submitted_via='public_form', moderation_status='pending', is_published=False,
            consent_to_publish=True, consent_at=timezone.now(), withdraw_token=secrets.token_urlsafe(32),
            content_hash=digest)
        log(t, 'submitted', 'author', 'Website form; consent to publish given')
    return t


def withdraw(token):
    """The author withdraws consent: unpublish and erase the text and name; the history row stays."""
    if not token or len(token) < 30:
        return None
    with transaction.atomic():
        t = ClinicTestimonial.objects.select_for_update().filter(withdraw_token=token).first()
        if t is None or t.moderation_status == 'withdrawn':
            return t
        t.is_published, t.moderation_status, t.withdrawn_at = False, 'withdrawn', timezone.now()
        t.consent_to_publish = False
        t.patient_name, t.patient_designation, t.review_text, t.owner_reply = gettext('Withdrawn'), '', '', ''
        if t.photo:
            t.photo.delete(save=False)
        t.save()
        log(t, 'withdrawn', 'author', 'Consent withdrawn; content erased')
    return t


# ── staff moderation ─────────────────────────────────────────────────────────────────────────────────────

ACTIONS = {
    'publish': ('approved', True), 'unpublish': (None, False), 'approve': ('approved', None),
    'reject': ('rejected', False), 'spam': ('spam', False), 'reopen': ('pending', False),
}


def moderate(t, action, user, note=''):
    """Apply a moderation action. Returns an error message, or '' on success."""
    if action not in ACTIONS:
        return gettext('Unknown action.')
    if t.moderation_status == 'withdrawn':
        return gettext('The author withdrew this review; it cannot be published again.')
    status, published = ACTIONS[action]
    if published and t.submitted_via == 'public_form' and not t.consent_to_publish:
        return gettext('The author has not agreed to publication.')
    if status:
        t.moderation_status = status
    if published is not None:
        t.is_published = published
    t.save(update_fields=['moderation_status', 'is_published'])
    log(t, action, user.get_username() if user else '', note)
    return ''


# ── story video thumbnails ───────────────────────────────────────────────────────────────────────────────

ASPECTS = {'16:9': (16, 9), '4:5': (4, 5), '9:16': (9, 16)}
WIDTHS = (360, 720)
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


def validate_image(upload):
    """Shared upload check (real image format, size, pixel limits, safe random name)."""
    from spinalcure.uploads import checked_image
    return checked_image(upload)


def crop_box(width, height, aspect, fx, fy):
    """Largest box of `aspect` inside the image, centred on the focal point (percent) and clamped to the edges."""
    aw, ah = ASPECTS[aspect]
    if width * ah > height * aw:              # image wider than target: full height
        h, w = height, round(height * aw / ah)
    else:
        w, h = width, round(width * ah / aw)
    left = min(max(round(width * fx / 100 - w / 2), 0), width - w)
    top = min(max(round(height * fy / 100 - h / 2), 0), height - h)
    return left, top, left + w, top + h


def avif_supported():
    from PIL import features
    try:
        return bool(features.check('avif'))
    except Exception:
        return False


def rendition_name(video, aspect, width, fmt):
    stamp = int(video.updated_at.timestamp()) if video.updated_at else 0
    key = hashlib.sha1(f'{video.thumbnail.name}|{video.focal_x}|{video.focal_y}|{stamp}'.encode()).hexdigest()[:16]
    return f'stories/r/{key}_{aspect.replace(":", "x")}_{width}.{fmt}'


def rendition_url(video, aspect, width, fmt='webp'):
    """URL of a cropped, resized rendition of the uploaded thumbnail; generated once, then served from storage."""
    if not video.thumbnail:
        return ''
    name = rendition_name(video, aspect, width, fmt)
    if not default_storage.exists(name):
        from PIL import Image, ImageOps
        try:
            with video.thumbnail.open('rb') as fh:
                img = ImageOps.exif_transpose(Image.open(fh))
                img = img.convert('RGB').crop(crop_box(img.width, img.height, aspect, video.focal_x, video.focal_y))
            aw, ah = ASPECTS[aspect]
            img = img.resize((width, round(width * ah / aw)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format=fmt.upper(), quality=60 if fmt == 'avif' else 80)
            default_storage.save(name, ContentFile(buf.getvalue()))
        except Exception:
            logger.exception('Thumbnail rendition failed for story %s', video.pk)
            return ''
    return default_storage.url(name)


FRAME_FILES = {'frame1': '1.jpg', 'frame2': '2.jpg', 'frame3': '3.jpg', 'platform': 'hqdefault.jpg'}


def frame_url(video, source):
    if video.platform != 'youtube' or source not in FRAME_FILES:
        return ''
    return f'https://i.ytimg.com/vi/{video.video_id}/{FRAME_FILES[source]}'


def import_frame(video, source):
    """Copy one of YouTube's frames of this (already public) video into our storage as the thumbnail."""
    url = frame_url(video, source)
    if not url:
        raise ValueError(gettext('Frames are only available for YouTube videos.'))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'SpinalCure'}), timeout=10) as r:
            data = r.read(MAX_UPLOAD_BYTES + 1)
    except Exception:
        raise ValueError(gettext('Could not download that frame. Try again or upload an image.'))
    upload = ContentFile(data, name=f'{source}.jpg')
    validate_image(upload)
    if video.thumbnail:
        video.thumbnail.delete(save=False)
    video.thumbnail.save(f'{source}.jpg', upload, save=False)
    video.thumbnail_source = source
