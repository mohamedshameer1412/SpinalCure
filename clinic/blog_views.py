"""
Public-facing blog views for SpinalCure portfolio.
"""
from django.shortcuts import render, get_object_or_404
from .blog_models import BlogPost, BlogTag
from .models import Practitioner


def blog_list_view(request):
    """Public blog listing page — all published posts."""
    posts = BlogPost.objects.filter(status='published').select_related('author').prefetch_related('tags')

    # Filter by tag
    tag_slug = request.GET.get('tag', '')
    selected_tag = None
    if tag_slug:
        selected_tag = get_object_or_404(BlogTag, slug=tag_slug)
        posts = posts.filter(tags=selected_tag)

    # Filter by author (practitioner)
    author_id = request.GET.get('author', '')
    selected_author = None
    if author_id:
        selected_author = get_object_or_404(Practitioner, pk=author_id)
        posts = posts.filter(author=selected_author)

    # All tags and authors for filter UI
    all_tags = BlogTag.objects.filter(posts__status='published').distinct()
    all_authors = Practitioner.objects.filter(blog_posts__status='published', is_active=True).distinct()

    from clinic.models import ClinicProfile
    clinic = ClinicProfile.objects.first()

    context = {
        'posts': posts,
        'all_tags': all_tags,
        'all_authors': all_authors,
        'selected_tag': selected_tag,
        'selected_author': selected_author,
        'clinic': clinic,
    }
    return render(request, 'clinic/blog_list.html', context)


def blog_detail_view(request, slug):
    """Public blog detail / article page."""
    post = get_object_or_404(BlogPost, slug=slug, status='published')

    # Related posts: same tags, exclude self, limit 3
    related = BlogPost.objects.filter(
        status='published',
        tags__in=post.tags.all()
    ).exclude(pk=post.pk).distinct()[:3]

    from clinic.models import ClinicProfile
    clinic = ClinicProfile.objects.first()

    context = {
        'post': post,
        'related_posts': related,
        'clinic': clinic,
    }
    return render(request, 'clinic/blog_detail.html', context)
