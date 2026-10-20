"""Public testimonials search (reviews + reels/shorts) and admin management of videos and problem categories."""
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from spinalcure.decorators import superadmin_required
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
    videos = TestimonialVideo.objects.filter(is_published=True).select_related('problem')
    if problem:
        reviews, videos = reviews.filter(problem=problem), videos.filter(problem=problem)
    if q:
        reviews = reviews.filter(
            Q(patient_name__icontains=q) | Q(review_text__icontains=q) | Q(owner_reply__icontains=q)
            | Q(patient_designation__icontains=q) | _problem_q('problem', q))
        videos = videos.filter(
            Q(title__icontains=q) | Q(patient_name__icontains=q) | Q(description__icontains=q) | _problem_q('problem', q))

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
        'reviews': reviews[:limit], 'videos': videos[:limit], 'more_url': '?' + urlencode({k: v for k, v in params.items() if v}) if more else '',
        'problems': ProblemCategory.objects.filter(is_active=True),
        'rating_range': range(1, 6),
        'kinds': [('all', gettext('All')), ('reviews', gettext('Reviews')), ('videos', gettext('Reels & Shorts'))],
    }
    ctx['total'] = total
    template = 'clinic/partials/testimonial_results.html' if request.headers.get('HX-Request') else 'clinic/testimonials_public.html'
    return render(request, template, ctx)


# ── Admin: videos ──────────────────────────────────────────────────────────

@superadmin_required
def admin_videos(request):
    if request.method == 'POST':
        v = TestimonialVideo(
            title=request.POST.get('title', '').strip(),
            patient_name=request.POST.get('patient_name', '').strip(),
            url=request.POST.get('url', '').strip(),
            description=request.POST.get('description', '').strip(),
            problem_id=request.POST.get('problem') or None,
            display_order=int(request.POST.get('display_order') or 0),
        )
        try:
            v.full_clean(exclude=['platform', 'video_id'])
            v.save()
            messages.success(request, gettext('Video "%(title)s" added.') % {'title': v.title})
        except ValidationError as e:
            messages.error(request, gettext('Could not save: %(e)s') % {'e': '; '.join(sum(e.message_dict.values(), []))})
        return redirect('admin_videos')
    return render(request, 'clinic/admin/videos.html', {
        'videos': TestimonialVideo.objects.select_related('problem'),
        'problems': ProblemCategory.objects.filter(is_active=True),
    })


@superadmin_required
@require_POST
def admin_video_toggle(request, pk):
    v = get_object_or_404(TestimonialVideo, pk=pk)
    v.is_published = not v.is_published
    v.save(update_fields=['is_published'])
    return redirect('admin_videos')


@superadmin_required
@require_POST
def admin_video_delete(request, pk):
    v = get_object_or_404(TestimonialVideo, pk=pk)
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
