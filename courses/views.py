from django.utils.translation import gettext
from django.contrib.auth.decorators import login_required
from spinalcure.rbac import has_capability, require_capability
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from datetime import datetime
import logging

from spinalcure.utils import SpinalCureExport, log_action
from courses.models import Course, CourseBatch, CourseRegistration, CourseFeedback
from courses.forms import CourseForm, CourseBatchForm
from courses import service as course_service
from events.service import EventError
import logging
from spinalcure.decorators import superadmin_required, require_pin_auth

logger = logging.getLogger(__name__)


# ── Course Admin CRUD ─────────────────────────────────────────────────────────

@require_capability('events.registrations')
def course_list_view(request):
    query = request.GET.get('q', '')
    courses = Course.objects.all().order_by('-created_at')
    
    if query:
        courses = courses.filter(Q(title__icontains=query) | Q(description__icontains=query))
        
    # Pagination
    paginator = Paginator(courses, 9)  # Show 9 courses per page (3x3 grid)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Export URLs
    base_export_params = f"?q={query}" if query else ""
    
    context = {
        'courses': page_obj,
        'search_query': query,
        'export_courses_excel_url': reverse('export_courses_excel') + base_export_params,
        'export_courses_csv_url': reverse('export_courses_csv') + base_export_params,
        'export_courses_pdf_url': reverse('export_courses_pdf') + base_export_params,
        'export_courses_copy_url': reverse('export_courses_copy') + base_export_params,
        'export_courses_print_url': reverse('export_courses_print') + base_export_params,
    }
    
    if request.headers.get('HX-Request'):
        return render(request, 'courses/partials/course_list_partial.html', context)
        
    return render(request, 'courses/course_list.html', context)


@require_capability('events.manage')
def course_create_view(request):
    form = CourseForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        course = form.save()
        log_action(request, 'create', 'Course', course.title, object_id=course.id)
        messages.success(request, gettext('Course "%(title)s" created successfully.') % {'title': course.title})
        return redirect('course_list')
    return render(request, 'courses/course_form.html', {'form': form, 'title': 'Create Course'})


@login_required
@require_pin_auth('course_list')
def course_edit_view(request, pk):
    if not has_capability(request.user, 'events.manage'):
        messages.error(request, gettext('Permission denied.'))
        return redirect('course_list')
    course = get_object_or_404(Course, pk=pk)
    form = CourseForm(request.POST or None, request.FILES or None, instance=course)
    if form.is_valid():
        form.save()
        log_action(request, 'update', 'Course', course.title, object_id=pk)
        messages.success(request, gettext('Course "%(title)s" updated.') % {'title': course.title})
        return redirect('course_list')
    return render(request, 'courses/course_form.html', {'form': form, 'title': 'Edit Course', 'course': course})


@login_required
@require_http_methods(["POST"])
def toggle_course_publish(request, pk):
    if not has_capability(request.user, 'events.manage'):
        messages.error(request, gettext('Permission denied.'))
        return redirect('course_list')
    course = get_object_or_404(Course, pk=pk)
    course.is_published = not course.is_published
    course.save(update_fields=['is_published'])
    state = 'published' if course.is_published else 'hidden'
    messages.success(request, gettext('Course "%(title)s" %(state)s.') % {'title': course.title, 'state': state})
    return redirect('course_list')


@login_required
@require_http_methods(["POST"])
@require_pin_auth('course_list')
def course_delete_view(request, pk):
    if not has_capability(request.user, 'events.manage'):
        messages.error(request, gettext('Permission denied.'))
        return redirect('course_list')
    course = get_object_or_404(Course, pk=pk)
    title = course.title
    course_id = course.id
    course.delete()
    log_action(request, 'delete', 'Course', title, object_id=course_id)
    messages.success(request, gettext('Course "%(title)s" deleted.') % {'title': title})
    return redirect('course_list')


# ── Batch Admin CRUD ──────────────────────────────────────────────────────────

@require_capability('events.registrations')
def batch_list_view(request, course_pk):
    course = get_object_or_404(Course, pk=course_pk)
    batches = course.batches.annotate_registrations() if hasattr(course.batches, 'annotate_registrations') else course.batches.all()
    return render(request, 'courses/batch_list.html', {'course': course, 'batches': course.batches.all()})


@require_capability('events.manage')
def batch_create_view(request, course_pk):
    course = get_object_or_404(Course, pk=course_pk)
    form = CourseBatchForm(request.POST or None)
    if form.is_valid():
        batch = form.save(commit=False)
        batch.course = course
        # Only one batch can be active at a time
        if batch.is_active:
            course.batches.filter(is_active=True).update(is_active=False)
        batch.save()
        messages.success(request, gettext('Batch "%(name)s" created.') % {'name': batch.name})
        return redirect('batch_list', course_pk=course.pk)
    return render(request, 'courses/batch_form.html', {
        'form': form, 'course': course, 'title': 'Add Batch'
    })


@login_required
@require_pin_auth('course_list')
def batch_edit_view(request, pk):
    if not has_capability(request.user, 'events.manage'):
        messages.error(request, gettext('Permission denied.'))
        return redirect('course_list')
    batch = get_object_or_404(CourseBatch, pk=pk)
    form = CourseBatchForm(request.POST or None, instance=batch)
    if form.is_valid():
        b = form.save(commit=False)
        if b.is_active:
            batch.course.batches.exclude(pk=pk).filter(is_active=True).update(is_active=False)
        b.save()
        messages.success(request, gettext('Batch "%(name)s" updated.') % {'name': batch.name})
        return redirect('batch_list', course_pk=batch.course.pk)
    return render(request, 'courses/batch_form.html', {
        'form': form, 'course': batch.course, 'title': 'Edit Batch', 'batch': batch
    })


@login_required
@require_http_methods(["POST"])
@require_pin_auth('course_list')
def batch_delete_view(request, pk):
    if not has_capability(request.user, 'events.manage'):
        messages.error(request, gettext('Permission denied.'))
        return redirect('course_list')
    batch = get_object_or_404(CourseBatch, pk=pk)
    course_pk = batch.course.pk
    name = batch.name
    batch.delete()
    messages.success(request, gettext('Batch "%(name)s" deleted.') % {'name': name})
    return redirect('batch_list', course_pk=course_pk)


# ── Registrations & Feedback Admin ───────────────────────────────────────────

@require_capability('events.registrations')
def batch_registrations_view(request, pk):
    batch = get_object_or_404(CourseBatch, pk=pk)
    query = request.GET.get('q', '')
    registrations = batch.registrations.all()
    status = request.GET.get('status', '')
    if status in ('confirmed', 'waitlisted', 'cancelled'):
        registrations = registrations.filter(status=status)

    if query:
        registrations = registrations.filter(
            Q(name__icontains=query) |
            Q(email__icontains=query) |
            Q(phone__icontains=query)
        )
    
    registrations = registrations.order_by('-registered_at')
    
    # Pagination
    paginator = Paginator(registrations, 20)  # Show 20 registrations per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'batch': batch, 
        'registrations': page_obj,
        'search_query': query,
        'status': status,
        'can_manage_registrations': True,
        'waitlisted_count': batch.registrations.filter(status='waitlisted').count(),
        'export_batch_registrations_excel_url': reverse('export_batch_registrations_excel', kwargs={'pk': pk}),
        'export_batch_registrations_csv_url': reverse('export_batch_registrations_csv', kwargs={'pk': pk}),
        'export_batch_registrations_pdf_url': reverse('export_batch_registrations_pdf', kwargs={'pk': pk}),
        'export_batch_registrations_copy_url': reverse('export_batch_registrations_copy', kwargs={'pk': pk}),
        'export_batch_registrations_print_url': reverse('export_batch_registrations_print', kwargs={'pk': pk}),
    }
    
    if request.headers.get('HX-Request'):
        return render(request, 'courses/partials/batch_registrations_partial.html', context)

    return render(request, 'courses/batch_registrations.html', context)


@require_capability('events.registrations')
@require_http_methods(['POST'])
def batch_registration_cancel(request, pk, reg_pk):
    batch = get_object_or_404(CourseBatch, pk=pk)
    reg = get_object_or_404(CourseRegistration, pk=reg_pk, batch=batch)
    course_service.cancel_registration(reg, by_staff=True)
    log_action(request, 'update', 'CourseRegistration', f'Cancelled {reg.name} in {batch.name}', object_id=reg.pk)
    messages.success(request, gettext("Cancelled %(name)s's registration.") % {'name': reg.name})
    return redirect('batch_registrations', pk=batch.pk)


@require_capability('events.registrations')
@require_http_methods(['POST'])
def batch_promote_waitlist(request, pk):
    batch = get_object_or_404(CourseBatch, pk=pk)
    promoted = course_service.promote_waitlist(batch)
    for reg in promoted:
        messages.success(request, gettext('%(name)s was moved from the waitlist.') % {'name': reg.name})
    if not promoted:
        messages.info(request, gettext('No seat is free. Raise the capacity or cancel a registration first.'))
    return redirect('batch_registrations', pk=batch.pk)


@require_capability('events.manage')
def batch_feedback_admin_view(request, pk):
    batch = get_object_or_404(CourseBatch, pk=pk)
    feedbacks = batch.feedback.order_by('-submitted_at')
    return render(request, 'courses/batch_feedback_admin.html', {
        'batch': batch, 'feedbacks': feedbacks
    })


@require_capability('events.manage')
@require_http_methods(["POST"])
def toggle_batch_feedback(request, pk):
    batch = get_object_or_404(CourseBatch, pk=pk)
    batch.feedback_enabled = not batch.feedback_enabled
    batch.save(update_fields=['feedback_enabled'])
    state = 'enabled' if batch.feedback_enabled else 'disabled'
    messages.success(request, gettext('Feedback form %(state)s for batch "%(name)s".') % {'state': state, 'name': batch.name})
    return redirect('batch_feedback_admin', pk=pk)


@require_capability('events.manage')
@require_http_methods(["POST"])
def toggle_course_feedback_publish(request, feedback_pk):
    fb = get_object_or_404(CourseFeedback, pk=feedback_pk)
    fb.is_published = not fb.is_published
    fb.save(update_fields=['is_published'])
    state = 'published' if fb.is_published else 'unpublished'
    messages.success(request, gettext('Feedback by %(reviewer_name)s %(state)s.') % {'reviewer_name': fb.reviewer_name, 'state': state})
    return redirect('batch_feedback_admin', pk=fb.batch.pk)

# ── Export Logic ──

def _get_filtered_courses(request):
    query = request.GET.get('q', '')
    courses = Course.objects.prefetch_related('batches').order_by('-created_at')
    if query:
        courses = courses.filter(Q(title__icontains=query))
    return courses, query

def _course_mapping(c):
    return [c.title, c.description[:50], float(c.fees), c.duration, c.created_at.strftime('%Y-%m-%d')]

@require_capability('events.registrations')
def export_courses_excel(request):
    courses, _ = _get_filtered_courses(request)
    headers = ["Title", "Description", "Fees", "Duration", "Created"]
    return SpinalCureExport.to_excel(courses, headers, _course_mapping, "Courses", "courses")

@require_capability('events.registrations')
def export_courses_csv(request):
    courses, _ = _get_filtered_courses(request)
    headers = ["Title", "Description", "Fees", "Duration", "Created"]
    return SpinalCureExport.to_csv(courses, headers, _course_mapping, "courses")

@require_capability('events.registrations')
def export_courses_pdf(request):
    courses, query = _get_filtered_courses(request)
    headers = ["Title", "Fees", "Duration", "Created"]
    def pdf_mapping(c):
        return [c.title, f"₹{c.fees:,.2f}", c.duration, c.created_at.strftime('%Y-%m-%d')]
    title = f"Courses Catalog {'(Filtered)' if query else ''}"
    return SpinalCureExport.to_pdf(courses, headers, pdf_mapping, title, "courses")

@require_capability('events.registrations')
def export_courses_copy(request):
    courses, _ = _get_filtered_courses(request)
    headers = ["Title", "Fees", "Duration", "Created"]
    text = SpinalCureExport.to_text(courses, headers, _course_mapping)
    return HttpResponse(text, content_type='text/plain')

@require_capability('events.registrations')
def export_courses_print(request):
    courses, query = _get_filtered_courses(request)
    headers = ["Title", "Fees", "Duration", "Created"]
    rows = [[c.title, f"₹{c.fees:,.2f}", c.duration, c.created_at.strftime('%Y-%m-%d')] for c in courses]
    context = {
        'rows': rows,
        'title': 'Courses Report',
        'query': query,
        'headers': headers,
        'now': datetime.now(),
    }
    return render(request, 'exports/print_template.html', context)

# ── Batch Registration Export ──

def _batch_reg_mapping(r):
    return [r.name, r.email, r.phone, r.get_status_display(), r.registered_at.strftime('%Y-%m-%d %H:%M')]

@require_capability('events.registrations')
def export_batch_registrations_excel(request, pk):
    batch = get_object_or_404(CourseBatch, pk=pk)
    registrations = batch.registrations.all().order_by('-registered_at')
    headers = ["Name", "Email", "Phone", "Status", "Date"]
    return SpinalCureExport.to_excel(registrations, headers, _batch_reg_mapping, f"Reg - {batch.name}", "batch_registrations")

@require_capability('events.registrations')
def export_batch_registrations_csv(request, pk):
    batch = get_object_or_404(CourseBatch, pk=pk)
    registrations = batch.registrations.all().order_by('-registered_at')
    headers = ["Name", "Email", "Phone", "Status", "Date"]
    return SpinalCureExport.to_csv(registrations, headers, _batch_reg_mapping, "batch_registrations")

@require_capability('events.registrations')
def export_batch_registrations_pdf(request, pk):
    batch = get_object_or_404(CourseBatch, pk=pk)
    registrations = batch.registrations.all().order_by('-registered_at')
    headers = ["Name", "Email", "Phone", "Status", "Date"]
    title = f"Batch Registrations: {batch.name}"
    return SpinalCureExport.to_pdf(registrations, headers, _batch_reg_mapping, title, "batch_registrations")

@require_capability('events.registrations')
def export_batch_registrations_copy(request, pk):
    batch = get_object_or_404(CourseBatch, pk=pk)
    registrations = batch.registrations.all().order_by('-registered_at')
    headers = ["Name", "Email", "Phone", "Status", "Date"]
    text = SpinalCureExport.to_text(registrations, headers, _batch_reg_mapping)
    return HttpResponse(text, content_type='text/plain')

@require_capability('events.registrations')
def export_batch_registrations_print(request, pk):
    batch = get_object_or_404(CourseBatch, pk=pk)
    registrations = batch.registrations.all().order_by('-registered_at')
    headers = ["Name", "Email", "Phone", "Status", "Date"]
    rows = [_batch_reg_mapping(r) for r in registrations]
    context = {
        'rows': rows,
        'title': f'Registrations: {batch.name}',
        'headers': headers,
        'now': datetime.now(),
    }
    return render(request, 'exports/print_template.html', context)
