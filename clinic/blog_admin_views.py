"""
Admin (dashboard) views for Blog management.
Only superadmins and doctors can write/manage blogs.
"""
from django.utils.translation import gettext
from spinalcure.rbac import has_capability
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .blog_models import BlogPost, BlogTag
from .models import Practitioner


@login_required
def admin_blog_list(request):
    """List all blog posts (admin panel)."""
    posts = BlogPost.objects.select_related('author').prefetch_related('tags').order_by('-created_at')
    context = {'posts': posts}
    return render(request, 'clinic/admin/blog_list.html', context)


@login_required
def admin_blog_create(request):
    """Create a new blog post."""
    if not has_capability(request.user, 'website.manage'):
        messages.error(request, gettext('You do not have permission to create blog posts.'))
        return redirect('dashboard')

    all_tags = BlogTag.objects.all()
    practitioners = Practitioner.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        excerpt = request.POST.get('excerpt', '').strip()
        status = request.POST.get('status', 'draft')
        author_id = request.POST.get('author', '')
        author_name_override = request.POST.get('author_name_override', '').strip()
        meta_description = request.POST.get('meta_description', '').strip()
        tag_ids = request.POST.getlist('tags')

        if not title or not content:
            messages.error(request, gettext('Title and Content are required.'))
        else:
            post = BlogPost(
                title=title,
                content=content,
                excerpt=excerpt,
                status=status,
                author_name_override=author_name_override,
                meta_description=meta_description,
            )
            if author_id:
                post.author = get_object_or_404(Practitioner, pk=author_id)

            if request.FILES.get('cover_image'):
                post.cover_image = request.FILES['cover_image']

            post.save()

            # Set tags
            if tag_ids:
                post.tags.set(BlogTag.objects.filter(pk__in=tag_ids))

            messages.success(request, gettext('Blog post "%(title)s" created successfully.') % {'title': title})
            return redirect('admin_blog_list')

    context = {
        'all_tags': all_tags,
        'practitioners': practitioners,
        'status_choices': BlogPost.STATUS_CHOICES,
    }
    return render(request, 'clinic/admin/blog_form.html', context)


@login_required
def admin_blog_edit(request, pk):
    """Edit an existing blog post."""
    if not has_capability(request.user, 'website.manage'):
        messages.error(request, gettext('You do not have permission to edit blog posts.'))
        return redirect('dashboard')

    post = get_object_or_404(BlogPost, pk=pk)
    all_tags = BlogTag.objects.all()
    practitioners = Practitioner.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        post.title = request.POST.get('title', '').strip()
        post.content = request.POST.get('content', '').strip()
        post.excerpt = request.POST.get('excerpt', '').strip()
        post.status = request.POST.get('status', 'draft')
        post.author_name_override = request.POST.get('author_name_override', '').strip()
        post.meta_description = request.POST.get('meta_description', '').strip()
        tag_ids = request.POST.getlist('tags')

        author_id = request.POST.get('author', '')
        if author_id:
            post.author = get_object_or_404(Practitioner, pk=author_id)
        else:
            post.author = None

        if request.FILES.get('cover_image'):
            post.cover_image = request.FILES['cover_image']

        if not post.title or not post.content:
            messages.error(request, gettext('Title and Content are required.'))
        else:
            post.save()
            post.tags.set(BlogTag.objects.filter(pk__in=tag_ids))
            messages.success(request, gettext('Blog post "%(title)s" updated.') % {'title': post.title})
            return redirect('admin_blog_list')

    context = {
        'post': post,
        'all_tags': all_tags,
        'practitioners': practitioners,
        'status_choices': BlogPost.STATUS_CHOICES,
        'is_edit': True,
    }
    return render(request, 'clinic/admin/blog_form.html', context)


@login_required
def admin_blog_delete(request, pk):
    """Delete a blog post."""
    if not has_capability(request.user, 'website.manage'):
        messages.error(request, gettext('You do not have permission to delete blog posts.'))
        return redirect('dashboard')

    post = get_object_or_404(BlogPost, pk=pk)
    if request.method == 'POST':
        title = post.title
        post.delete()
        messages.success(request, gettext('Blog post "%(title)s" deleted.') % {'title': title})
    return redirect('admin_blog_list')


@login_required
def admin_tag_list(request):
    """Manage blog tags."""
    if not has_capability(request.user, 'website.manage'):
        messages.error(request, gettext('Permission denied.'))
        return redirect('dashboard')

    tags = BlogTag.objects.all()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            name = request.POST.get('name', '').strip()
            if name:
                tag, created = BlogTag.objects.get_or_create(name=name)
                if created:
                    messages.success(request, gettext('Tag "%(name)s" created.') % {'name': name})
                else:
                    messages.warning(request, gettext('Tag "%(name)s" already exists.') % {'name': name})
        elif action == 'delete':
            tag_id = request.POST.get('tag_id')
            tag = get_object_or_404(BlogTag, pk=tag_id)
            tag.delete()
            messages.success(request, gettext('Tag deleted.'))
        return redirect('admin_blog_tags')

    context = {'tags': tags}
    return render(request, 'clinic/admin/blog_tags.html', context)
