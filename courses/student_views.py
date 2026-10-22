"""Students: the relationship side of courses. A directory, one profile per person (details, batches, notes and
follow-ups), ID cards, and the public pages a student uses (card images, verification)."""
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from spinalcure.rbac import require_capability
from spinalcure.utils import log_action

from . import idcard, service
from .forms import StudentProfileForm
from .models import CourseBatch, CourseRegistration, Student, StudentNote

CAP = 'events.registrations'
SIDES = ('front', 'back')


def _lang(request):
    from django.utils import translation
    return translation.get_language() or 'en'


@require_capability(CAP)
def student_list(request):
    q = request.GET.get('q', '').strip()[:100]
    profile = request.GET.get('profile', '')
    qs = Student.objects.annotate(n_batches=Count('registrations'))
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(email__icontains=q) | Q(student_code__icontains=q))
    if profile == 'incomplete':
        qs = qs.filter(profile_completed_at__isnull=True)
    elif profile == 'complete':
        qs = qs.filter(profile_completed_at__isnull=False)
    elif profile == 'follow_up':
        qs = qs.filter(notes__follow_up_on__lte=timezone.localdate(), notes__done=False).distinct()
    page = Paginator(qs.order_by('-created_at'), 20).get_page(request.GET.get('page'))
    ctx = {'students': page, 'q': q, 'profile': profile, 'total': Student.objects.count(),
           'incomplete': Student.objects.filter(profile_completed_at__isnull=True).count(),
           'due': StudentNote.objects.filter(follow_up_on__lte=timezone.localdate(), done=False).count()}
    return render(request, 'courses/student_list.html', ctx)


@require_capability(CAP)
def student_detail(request, pk):
    st = get_object_or_404(Student, pk=pk)
    regs = list(st.registrations.select_related('batch__course').order_by('-registered_at'))
    reg = idcard.best_registration(st)
    return render(request, 'courses/student_detail.html', {
        'st': st, 'regs': regs, 'notes': st.notes.select_related('author')[:100], 'kinds': StudentNote.KIND_CHOICES,
        'card_reg': reg, 'link': (request.build_absolute_uri(service.manage_path(reg)) if reg else ''),
        'same_phone': Student.objects.filter(phone_key=st.phone_key).exclude(pk=st.pk)[:5] if st.phone_key else [],
        'today': timezone.localdate()})


@require_capability(CAP)
def student_edit(request, pk):
    st = get_object_or_404(Student, pk=pk)
    form = StudentProfileForm(request.POST or None, request.FILES or None, instance=st, staff=True)
    extra = ('name', 'phone')
    if request.method == 'POST' and form.is_valid():
        st = form.save(commit=False)
        st.name = request.POST.get('name', st.name).strip()[:200] or st.name
        phone = request.POST.get('phone', st.phone).strip()[:20]
        if phone:
            from events.service import phone_key
            st.phone, st.phone_key = phone, phone_key(phone)
        st.save()
        log_action(request, 'update', 'Student', st.student_code, object_id=st.pk)
        messages.success(request, gettext('Student details saved.'))
        return redirect('student_detail', pk=st.pk)
    return render(request, 'courses/student_form.html', {'st': st, 'form': form})


@require_capability(CAP)
@require_POST
def student_note_add(request, pk):
    st = get_object_or_404(Student, pk=pk)
    text = request.POST.get('text', '').strip()[:2000]
    kind = request.POST.get('kind') if request.POST.get('kind') in dict(StudentNote.KIND_CHOICES) else 'note'
    when = None
    if request.POST.get('follow_up_on'):
        try:
            from datetime import date
            when = date.fromisoformat(request.POST['follow_up_on'])
        except ValueError:
            when = None
    if not text:
        messages.error(request, gettext('Write something first.'))
    else:
        StudentNote.objects.create(student=st, author=request.user, kind='follow_up' if when and kind == 'note' else kind,
                                   text=text, follow_up_on=when)
        messages.success(request, gettext('Note added.'))
    return redirect('student_detail', pk=st.pk)


@require_capability(CAP)
@require_POST
def student_note_done(request, pk, note_pk):
    note = get_object_or_404(StudentNote, pk=note_pk, student_id=pk)
    note.done = not note.done
    note.save(update_fields=['done'])
    return redirect('student_detail', pk=pk)


@require_capability(CAP)
@require_POST
def student_send_link(request, pk):
    """Email the student the link to complete their details again (e.g. after fixing their email address)."""
    st = get_object_or_404(Student, pk=pk)
    reg = idcard.best_registration(st)
    if not reg or reg.status != 'confirmed':
        messages.error(request, gettext('This student has no confirmed place.'))
    elif not (reg.email or st.email):
        messages.error(request, gettext('No email address yet. Add one, or share the link by WhatsApp.'))
    elif st.profile_complete:
        messages.info(request, gettext('This student has already completed their details.'))
    else:
        service.request_profile(reg, resend=True)
        StudentNote.objects.create(student=st, author=request.user, kind='email', text=gettext('Sent the "complete your details" link.'))
        messages.success(request, gettext('Link emailed to %(email)s.') % {'email': reg.email or st.email})
    return redirect('student_detail', pk=st.pk)


@require_capability(CAP)
@require_POST
def batch_request_feedback(request, pk):
    batch = get_object_or_404(CourseBatch, pk=pk)
    sent = service.request_feedback(batch)
    log_action(request, 'update', 'CourseBatch', f'Requested feedback from {batch.name}', object_id=batch.pk)
    messages.success(request, gettext('Feedback is open. %(n)s student(s) were emailed their link.') % {'n': sent})
    return redirect('batch_registrations', pk=batch.pk)


@require_capability(CAP)
@require_POST
def batch_remind_profiles(request, pk):
    batch = get_object_or_404(CourseBatch, pk=pk)
    n = 0
    for reg in batch.registrations.filter(status='confirmed', student__profile_completed_at__isnull=True).select_related('student', 'batch__course'):
        if service.request_profile(reg, resend=True):
            n += 1
    messages.success(request, gettext('Reminder emailed to %(n)s student(s).') % {'n': n})
    return redirect('batch_registrations', pk=batch.pk)


# ── cards ──────────────────────────────────────────────────────────────────────────────────────

def _card_response(reg, side, request, filename):
    if not reg or not reg.student_id or not reg.student.profile_complete:
        raise Http404
    resp = HttpResponse(idcard.png(reg, side, 2, _lang(request)), content_type='image/png')
    resp['Content-Disposition'] = f'inline; filename="{filename}"'
    resp['Cache-Control'] = 'private, no-store'
    return resp


@require_capability(CAP)
@never_cache
def student_card_png(request, pk, side):
    if side not in SIDES:
        raise Http404
    st = get_object_or_404(Student, pk=pk)
    return _card_response(idcard.best_registration(st), side, request, f'student-{st.student_code}-{side}.png')


@require_capability(CAP)
@never_cache
def student_card_pdf(request, pk):
    st = get_object_or_404(Student, pk=pk)
    return _pdf(idcard.best_registration(st), request, st)


def _pdf(reg, request, st):
    if not reg or not st.profile_complete:
        raise Http404
    resp = HttpResponse(idcard.pdf(reg, _lang(request)), content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="student-{st.student_code}.pdf"'
    resp['Cache-Control'] = 'private, no-store'
    return resp


@never_cache
def my_card_png(request, token, side):
    """The student's own card, opened from the private link in their email."""
    if side not in SIDES or len(token) > 64:
        raise Http404
    reg = get_object_or_404(CourseRegistration.objects.select_related('student', 'batch__course'), access_token=token)
    return _card_response(reg, side, request, f'student-id-{side}.png')


@never_cache
def my_card_pdf(request, token):
    if len(token) > 64:
        raise Http404
    reg = get_object_or_404(CourseRegistration.objects.select_related('student', 'batch__course'), access_token=token)
    return _pdf(reg, request, reg.student)


def student_verify(request, code):
    """Public: confirms a student card is real. Shows the first name, course and standing only, never contact details."""
    if len(code) > 12:
        raise Http404
    st = Student.objects.filter(student_code=code.upper()).first()
    reg = idcard.best_registration(st) if st and st.profile_complete else None
    status = idcard._status(reg) if reg else None
    return render(request, 'courses/student_verify.html', {
        'st': st if reg else None, 'reg': reg, 'status': status, 'first_name': (st.name.split() or [''])[0] if reg else '',
        'valid_until': idcard.valid_until(reg) if reg else None})
