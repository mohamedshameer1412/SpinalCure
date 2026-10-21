"""Public testimonials search (reviews + reels/shorts) and admin management of videos and problem categories."""
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from spinalcure.decorators import superadmin_required
from . import stories
from .models import ClinicTestimonial, ProblemCategory, TestimonialVideo

TYPES = ('all', 'reviews', 'videos')
PAGE = 24  # cards per section; "Show more" adds another page


def _problem_q(prefix, q):
    """Match a free-text query against a problem's name and keywords (so 'disc' finds 'Slip Disc')."""
    return Q(**{f'{prefix}__name__icontains': q}) | Q(**{f'{prefix}__keywords__icontains': q})


def testimonials_page(request):
    q = request.GET.get('q', '').strip()[:100]
    kind = request.GET.get('type', 'all')
    if kind not in TYPES:
        kind = 'all'
    problem = ProblemCategory.objects.filter(slug=request.GET.get('problem', ''), is_active=True).first()

    reviews = ClinicTestimonial.objects.filter(is_published=True).select_related('problem')
    videos = TestimonialVideo.objects.filter(is_published=True).exclude(consent_status='withdrawn').select_related('problem')
    if problem:
        reviews, videos = reviews.filter(problem=problem), videos.filter(problem=problem)
    if q:
        reviews = reviews.filter(
            Q(patient_name__icontains=q) | Q(review_text__icontains=q) | Q(owner_reply__icontains=q)
            | Q(patient_designation__icontains=q) | _problem_q('problem', q))
        videos = videos.filter(
            Q(title__icontains=q) | Q(patient_name__icontains=q) | Q(description__icontains=q) | Q(transcript__icontains=q)
            | _problem_q('problem', q))

    try:
        limit = min(max(int(request.GET.get('limit', PAGE)), PAGE), 500)
    except ValueError:
        limit = PAGE
    reviews = list(reviews.distinct()) if kind != 'videos' else []
    videos = list(videos.distinct()) if kind != 'reviews' else []
    total = len(reviews) + len(videos)
    more = len(reviews) > limit or len(videos) > limit
    params = {'q': q, 'problem': problem.slug if problem else '', 'type': kind, 'limit': limit + PAGE}
    ctx = {
        'q': q, 'kind': kind, 'selected_problem': problem,
        'reviews': reviews[:limit], 'videos': stories.with_slots(videos[:limit]), 'more_url': '?' + urlencode({k: v for k, v in params.items() if v}) if more else '',
        'problems': ProblemCategory.objects.filter(is_active=True),
        'rating_range': range(1, 6),
        'kinds': [('all', gettext('All')), ('reviews', gettext('Reviews')), ('videos', gettext('Reels & Shorts'))],
    }
    ctx['total'] = total
    ctx['review_form_token'] = stories.form_token()
    template = 'clinic/partials/testimonial_results.html' if request.headers.get('HX-Request') else 'clinic/testimonials_public.html'
    return render(request, template, ctx)


# ── Admin: videos ──────────────────────────────────────────────────────────

def _int(value, default=0, lo=0, hi=10**6):
    try:
        return min(max(int(value), lo), hi)
    except (TypeError, ValueError):
        return default


def _apply_video_form(v, post):
    """Copy the text fields of the video form onto v (no files)."""
    from datetime import date
    v.title = post.get('title', '').strip()[:200]
    v.patient_name = post.get('patient_name', '').strip()[:200]
    v.url = post.get('url', '').strip()
    v.description = post.get('description', '').strip()
    v.problem_id = post.get('problem') or None
    v.display_order = _int(post.get('display_order'))
    v.language = post.get('language') if post.get('language') in dict(TestimonialVideo._meta.get_field('language').choices) else 'en'
    v.transcript = post.get('transcript', '').strip()
    if post.get('consent_status') in dict(TestimonialVideo.CONSENT_CHOICES):
        v.consent_status = post['consent_status']
    v.consent_note = post.get('consent_note', '').strip()[:300]
    try:
        v.consent_date = date.fromisoformat(post['consent_date']) if post.get('consent_date') else None
    except ValueError:
        v.consent_date = None
    if post.get('layout') in dict(TestimonialVideo.LAYOUT_CHOICES):
        v.layout = post['layout']
    v.focal_x, v.focal_y = _int(post.get('focal_x'), 50, 0, 100), _int(post.get('focal_y'), 50, 0, 100)


@superadmin_required
def admin_videos(request):
    if request.method == 'POST':
        v = TestimonialVideo()
        _apply_video_form(v, request.POST)
        # Goes live only with the patient's consent on file.
        v.is_published = v.consent_status == 'obtained' and request.POST.get('is_published') == 'on'
        try:
            v.full_clean(exclude=['platform', 'video_id'])
            v.save()
            if v.platform == 'youtube':
                try:
                    stories.import_frame(v, 'platform')
                    v.save()
                    stories.warm_renditions(v)
                except ValueError:
                    pass                                     # card falls back to YouTube's own thumbnail
            messages.success(request, gettext('Video "%(title)s" added.') % {'title': v.title})
            if not v.is_published:
                messages.info(request, gettext('Saved as hidden. Record the patient\'s consent to publish it.'))
            return redirect('admin_video_edit', pk=v.pk)
        except ValidationError as e:
            messages.error(request, gettext('Could not save: %(e)s') % {'e': '; '.join(sum(e.message_dict.values(), []))})
        return redirect('admin_videos')
    status = request.GET.get('consent', '')
    videos = TestimonialVideo.objects.select_related('problem')
    if status in dict(TestimonialVideo.CONSENT_CHOICES):
        videos = videos.filter(consent_status=status)
    q = request.GET.get('q', '').strip()[:100]
    if q:
        videos = videos.filter(Q(title__icontains=q) | Q(patient_name__icontains=q) | Q(description__icontains=q))
    problem_filter = request.GET.get('problem', '')
    if problem_filter == 'none':
        videos = videos.filter(problem__isnull=True)
    elif problem_filter:
        videos = videos.filter(problem_id=problem_filter) if _is_uuid(problem_filter) else videos.none()
    from django.core.paginator import Paginator
    page = Paginator(videos, 25).get_page(request.GET.get('page'))
    return render(request, 'clinic/admin/videos.html', {
        'videos': page, 'page_obj': page, 'q': q, 'consent': status, 'problem_filter': problem_filter,
        'consent_choices': TestimonialVideo.CONSENT_CHOICES, 'language_choices': TestimonialVideo._meta.get_field('language').choices,
        'problems': ProblemCategory.objects.filter(is_active=True),
    })


@superadmin_required
def admin_video_edit(request, pk):
    v = get_object_or_404(TestimonialVideo, pk=pk)
    if request.method == 'POST':
        _apply_video_form(v, request.POST)
        try:
            if request.FILES.get('thumbnail'):
                upload = request.FILES['thumbnail']
                stories.validate_image(upload)
                if v.thumbnail:
                    v.thumbnail.delete(save=False)
                v.thumbnail, v.thumbnail_source = upload, 'upload'
            elif request.POST.get('thumbnail_action') in ('frame1', 'frame2', 'frame3', 'platform'):
                stories.import_frame(v, request.POST['thumbnail_action'])
            elif request.POST.get('thumbnail_action') == 'remove' and v.thumbnail:
                v.thumbnail.delete(save=False)
                v.thumbnail, v.thumbnail_source = None, 'platform'
            if request.POST.get('is_published') == 'on' and not v.can_publish:
                messages.warning(request, gettext('Not published: record the patient\'s consent first.'))
                v.is_published = False
            else:
                v.is_published = request.POST.get('is_published') == 'on'
            v.full_clean(exclude=['platform', 'video_id', 'thumbnail'])
            v.save()
            stories.warm_renditions(v)
            messages.success(request, gettext('Video "%(title)s" saved.') % {'title': v.title})
            return redirect('admin_video_edit', pk=v.pk)
        except ValueError as e:
            messages.error(request, str(e))
        except ValidationError as e:
            messages.error(request, gettext('Could not save: %(e)s') % {'e': '; '.join(sum(e.message_dict.values(), []))})
    return render(request, 'clinic/admin/video_form.html', {
        'video': v, 'problems': ProblemCategory.objects.filter(is_active=True),
        'consent_choices': TestimonialVideo.CONSENT_CHOICES, 'layout_choices': TestimonialVideo.LAYOUT_CHOICES,
        'language_choices': TestimonialVideo._meta.get_field('language').choices,
        'frames': [(k, stories.frame_url(v, k)) for k in ('platform', 'frame1', 'frame2', 'frame3')] if v.platform == 'youtube' else [],
        'aspects': ['16:9', '4:5', '9:16'],
    })


@superadmin_required
@require_POST
def admin_video_toggle(request, pk):
    v = get_object_or_404(TestimonialVideo, pk=pk)
    if not v.is_published and not v.can_publish:
        messages.error(request, gettext('Record the patient\'s consent before publishing this video.'))
        return redirect('admin_video_edit', pk=v.pk)
    v.is_published = not v.is_published
    v.save(update_fields=['is_published'])
    return redirect('admin_videos')


def _is_uuid(value):
    import uuid
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


@superadmin_required
@require_POST
def admin_video_problem(request, pk):
    """Quick tag from the list: which problem this story is about (drives the card colour and the public filter)."""
    v = get_object_or_404(TestimonialVideo, pk=pk)
    value = request.POST.get('problem', '')
    v.problem = ProblemCategory.objects.filter(pk=value, is_active=True).first() if _is_uuid(value) else None
    v.save(update_fields=['problem', 'updated_at'])
    return redirect(request.META.get('HTTP_REFERER') if url_has_allowed_host_and_scheme(
        request.META.get('HTTP_REFERER', ''), {request.get_host()}) else 'admin_videos')


@superadmin_required
@require_POST
def admin_video_delete(request, pk):
    v = get_object_or_404(TestimonialVideo, pk=pk)
    if v.thumbnail:
        v.thumbnail.delete(save=False)
    v.delete()
    messages.success(request, gettext('Video deleted.'))
    return redirect('admin_videos')


# ── Admin: problem categories ──────────────────────────────────────────────

@superadmin_required
def admin_problems(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, gettext('Enter a problem name.'))
        elif ProblemCategory.objects.filter(name__iexact=name).exists():
            messages.error(request, gettext('That problem already exists.'))
        else:
            ProblemCategory.objects.create(
                name=name, keywords=request.POST.get('keywords', '').strip(),
                order=ProblemCategory.objects.count())
            messages.success(request, gettext('Problem "%(name)s" added.') % {'name': name})
        return redirect('admin_problems')
    return render(request, 'clinic/admin/problems.html', {'problems': ProblemCategory.objects.all()})


@superadmin_required
@require_POST
def admin_problem_delete(request, pk):
    get_object_or_404(ProblemCategory, pk=pk).delete()  # testimonials/videos keep existing, problem becomes empty (SET_NULL)
    messages.success(request, gettext('Problem deleted.'))
    return redirect('admin_problems')
