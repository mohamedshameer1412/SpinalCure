"""Staff and student pages for attendance, certificates, fee instalments, study materials and the student portal."""
from datetime import date
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from spinalcure.rbac import require_capability
from spinalcure.utils import log_action

from . import certificate as cert_draw
from . import files, ops, service
from .models import (Attendance, Certificate, Course, CourseBatch, CourseFeePayment, CourseMaterial, CourseRegistration,
                     CourseSession, Student)

MANAGE = 'events.manage'
VIEW = 'events.registrations'


# ── attendance ───────────────────────────────────────────────────────────────────────────────────

@require_capability(VIEW)
def batch_attendance(request, pk):
    batch = get_object_or_404(CourseBatch.objects.select_related('course'), pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_session':
            try:
                day = date.fromisoformat(request.POST.get('date', ''))
            except ValueError:
                messages.error(request, gettext('Choose the date of the class.'))
            else:
                CourseSession.objects.create(batch=batch, date=day, title=request.POST.get('title', '').strip()[:160])
                messages.success(request, gettext('Class added. Tick who attended and save.'))
        elif action == 'delete_session':
            CourseSession.objects.filter(pk=request.POST.get('session'), batch=batch).delete()
            messages.success(request, gettext('Class removed.'))
        elif action == 'save':
            ticked = {tuple(k[2:].split('_', 1)) for k in request.POST if k.startswith('m_') and '_' in k[2:]}
            n = ops.save_attendance(batch, ticked)
            log_action(request, 'update', 'CourseBatch', f'Attendance saved for {batch.name}', object_id=batch.pk)
            messages.success(request, gettext('Attendance saved.'))
        elif action == 'min':
            try:
                batch.min_attendance_percent = min(max(int(request.POST.get('min_attendance_percent', 75)), 1), 100)
                batch.save(update_fields=['min_attendance_percent'])
                messages.success(request, gettext('Saved.'))
            except ValueError:
                messages.error(request, gettext('Enter a number from 1 to 100.'))
        return redirect('batch_attendance', pk=batch.pk)
    sessions = list(batch.sessions.all())
    regs = list(batch.registrations.filter(status='confirmed').select_related('student').order_by('name'))
    marks ={(m.session_id, m.registration_id): m.present for m in Attendance.objects.filter(session__in=sessions)}
    certs = {c.registration_id: c for c in Certificate.objects.filter(registration__in=regs)}
    rows = []
    for r in regs:
        cells = [(s, marks.get((s.pk, r.pk), False)) for s in sessions]
        present = sum(1 for _s, ok in cells if ok)
        pct = round(100 * present / len(sessions)) if sessions else None
        rows.append({'reg': r, 'cells': cells, 'present': present, 'pct': pct, 'ok': pct is not None and pct >= batch.min_attendance_percent,
                     'cert': certs.get(r.pk)})
    return render(request, 'courses/batch_attendance.html', {
        'batch': batch, 'sessions': sessions, 'rows': rows, 'today': timezone.localdate(),
        'eligible': sum(1 for r in rows if r['ok'] and not r['cert'])})


@require_capability(MANAGE)
@require_POST
def batch_issue_certificates(request, pk):
    batch = get_object_or_404(CourseBatch, pk=pk)
    issued, emailed = ops.issue_certificates(batch)
    log_action(request, 'create', 'Certificate', f'{issued} certificates for {batch.name}', object_id=batch.pk)
    if not batch.sessions.exists():
        messages.error(request, gettext('Add the classes and mark attendance first.'))
    else:
        messages.success(request, gettext('%(i)s certificate(s) issued, %(e)s emailed.') % {'i': issued, 'e': emailed})
    return redirect('batch_attendance', pk=batch.pk)


# ── certificates ─────────────────────────────────────────────────────────────────────────────────

def _certificate_response(cert):
    if cert.file:
        resp = FileResponse(cert.file.open('rb'), content_type='application/pdf')
    else:
        resp = HttpResponse(cert_draw.pdf_bytes(cert), content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="certificate-{cert.code}.pdf"'
    resp['Cache-Control'] = 'private, no-store'
    return resp


@require_capability(VIEW)
@never_cache
def certificate_staff_pdf(request, reg_pk):
    reg = get_object_or_404(CourseRegistration.objects.select_related('batch__course', 'student'), pk=reg_pk)
    cert = get_object_or_404(Certificate, registration=reg)
    return _certificate_response(cert)


@never_cache
def my_certificate_pdf(request, token):
    if len(token) > 64:
        raise Http404
    reg = get_object_or_404(CourseRegistration.objects.select_related('batch__course', 'student'), access_token=token)
    return _certificate_response(get_object_or_404(Certificate, registration=reg))


@require_capability(MANAGE)
@require_POST
def certificate_upload(request, reg_pk):
    """Replace the generated certificate with the clinic's own PDF for this student."""
    reg = get_object_or_404(CourseRegistration.objects.select_related('batch__course', 'student'), pk=reg_pk)
    upload = request.FILES.get('file')
    if not upload or not upload.name.lower().endswith('.pdf'):
        messages.error(request, gettext('Choose a PDF file.'))
        return redirect('student_detail', pk=reg.student_id)
    try:
        files.validate_material(upload)
    except ValidationError as e:
        messages.error(request, e.messages[0])
        return redirect('student_detail', pk=reg.student_id)
    cert, _ = Certificate.objects.get_or_create(registration=reg, defaults={'attendance_percent': ops.attendance_percent(reg)})
    cert.file = upload
    cert.save()
    ops.send_certificate(cert)
    messages.success(request, gettext('Certificate saved and emailed.') if cert.emailed_at else gettext('Certificate saved.'))
    return redirect('student_detail', pk=reg.student_id)


@require_capability(MANAGE)
@require_POST
def certificate_resend(request, reg_pk):
    reg = get_object_or_404(CourseRegistration.objects.select_related('batch__course', 'student'), pk=reg_pk)
    cert = get_object_or_404(Certificate, registration=reg)
    sent = ops.send_certificate(cert, resend=True)
    messages.success(request, gettext('Certificate emailed again.') if sent else gettext('No email address on file.'))
    return redirect('student_detail', pk=reg.student_id)


def certificate_verify(request, code):
    if len(code) > 14:
        raise Http404
    cert = Certificate.objects.select_related('registration__batch__course', 'registration__student').filter(code=code.upper()).first()
    reg = cert.registration if cert else None
    return render(request, 'courses/certificate_verify.html', {
        'cert': cert, 'reg': reg, 'first_name': (reg.student.name.split() or [''])[0] if reg and reg.student_id else ''})


# ── fees ─────────────────────────────────────────────────────────────────────────────────────────

def _money(value):
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return d.quantize(Decimal('0.01')) if d.is_finite() else None


@require_capability(VIEW)
@require_POST
def fee_payment_add(request, reg_pk):
    reg = get_object_or_404(CourseRegistration.objects.select_related('batch__course'), pk=reg_pk)
    amount = _money(request.POST.get('amount', ''))
    if amount is None or amount <= 0 or amount > Decimal('9999999'):
        messages.error(request, gettext('Enter the amount received.'))
    else:
        try:
            paid_on = date.fromisoformat(request.POST.get('paid_on', '')) if request.POST.get('paid_on') else timezone.localdate()
        except ValueError:
            paid_on = timezone.localdate()
        mode = request.POST.get('mode') if request.POST.get('mode') in dict(CourseFeePayment.MODE_CHOICES) else 'cash'
        CourseFeePayment.objects.create(registration=reg, amount=amount, paid_on=paid_on, mode=mode, recorded_by=request.user,
                                        reference=request.POST.get('reference', '').strip()[:80],
                                        note=request.POST.get('note', '').strip()[:200])
        log_action(request, 'create', 'CourseFeePayment', f'{amount} from {reg.name}', object_id=reg.pk)
        messages.success(request, gettext('Payment recorded.'))
    return redirect('student_detail', pk=reg.student_id)


@require_capability(MANAGE)
@require_POST
def fee_payment_delete(request, pay_pk):
    pay = get_object_or_404(CourseFeePayment.objects.select_related('registration'), pk=pay_pk)
    sid = pay.registration.student_id
    log_action(request, 'delete', 'CourseFeePayment', f'{pay.amount} from {pay.registration.name}', object_id=pay.pk)
    pay.delete()
    messages.success(request, gettext('Payment removed.'))
    return redirect('student_detail', pk=sid)


@require_capability(MANAGE)
@require_POST
def fee_override(request, reg_pk):
    """Agree a different fee for this student (scholarship, discount). Empty goes back to the course fee."""
    reg = get_object_or_404(CourseRegistration, pk=reg_pk)
    raw = request.POST.get('fee', '').strip()
    amount = _money(raw) if raw else None
    if raw and (amount is None or amount < 0):
        messages.error(request, gettext('Enter a valid fee.'))
    else:
        reg.fee_override = amount
        reg.save(update_fields=['fee_override'])
        messages.success(request, gettext('Fee updated.'))
    return redirect('student_detail', pk=reg.student_id)


# ── merging duplicates ───────────────────────────────────────────────────────────────────────────

@require_capability(MANAGE)
@require_POST
def student_merge(request, pk, other_pk):
    keep = get_object_or_404(Student, pk=pk)
    other = get_object_or_404(Student, pk=other_pk)
    if keep.pk == other.pk:
        raise Http404
    ops.merge_students(keep, other)
    log_action(request, 'update', 'Student', f'Merged {other.student_code} into {keep.student_code}', object_id=keep.pk)
    messages.success(request, gettext('Merged into this student.'))
    return redirect('student_detail', pk=keep.pk)


# ── study materials ──────────────────────────────────────────────────────────────────────────────

class MaterialForm(forms.ModelForm):
    class Meta:
        model = CourseMaterial
        fields = ['title', 'kind', 'url', 'file', 'batch', 'description', 'order', 'is_published']

    def __init__(self, *args, course, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['batch'].queryset = course.batches.all()
        self.fields['batch'].empty_label = gettext('Every batch of this course')
        self.fields['kind'].required = False
        self.fields['order'].required = False
        self.fields['file'].validators.append(files.validate_material)
        for f in self.fields.values():
            f.widget.attrs.setdefault('class', 'w-full')
        self.fields['file'].widget.attrs.pop('class', None)
        self.fields['is_published'].widget.attrs.pop('class', None)

    def clean(self):
        data = super().clean()
        upload, url = data.get('file'), data.get('url')
        if not upload and not url:
            raise ValidationError(gettext('Add a link, or upload a file.'))
        if upload and url:
            raise ValidationError(gettext('Use either a link or a file, not both.'))
        if upload:
            data['kind'] = files.kind_for(upload.name)
        elif not data.get('kind') or data['kind'] in ('pdf', 'doc'):
            data['kind'] = 'link'
        return data


@require_capability(MANAGE)
def course_materials(request, course_pk):
    course = get_object_or_404(Course, pk=course_pk)
    form = MaterialForm(request.POST or None, request.FILES or None, course=course)
    if request.method == 'POST' and form.is_valid():
        m = form.save(commit=False)
        m.course = course
        m.kind = form.cleaned_data['kind']
        m.save()
        messages.success(request, gettext('Material added.'))
        return redirect('course_materials', course_pk=course.pk)
    return render(request, 'courses/course_materials.html', {
        'course': course, 'form': form, 'materials': course.materials.select_related('batch')})


@require_capability(MANAGE)
@require_POST
def material_toggle(request, pk):
    m = get_object_or_404(CourseMaterial, pk=pk)
    m.is_published = not m.is_published
    m.save(update_fields=['is_published'])
    return redirect('course_materials', course_pk=m.course_id)


@require_capability(MANAGE)
@require_POST
def material_delete(request, pk):
    m = get_object_or_404(CourseMaterial, pk=pk)
    cid = m.course_id
    m.delete()
    messages.success(request, gettext('Material removed.'))
    return redirect('course_materials', course_pk=cid)


@never_cache
def my_material(request, token, pk):
    """An uploaded material, only for the confirmed student whose private link this is."""
    if len(token) > 64:
        raise Http404
    reg = get_object_or_404(CourseRegistration.objects.select_related('batch__course'), access_token=token)
    m = get_object_or_404(ops.materials_for(reg), pk=pk)
    if not m.file:
        raise Http404
    resp = FileResponse(m.file.open('rb'), as_attachment=(m.kind != 'video'), filename=f'{m.title[:60]}{m.file.name[m.file.name.rfind("."):]}')
    resp['Cache-Control'] = 'private, no-store'
    return resp


# ── the student portal ───────────────────────────────────────────────────────────────────────────

PORTAL_SESSION_KEY = 'student_portal_email'


@ratelimit(key='ip', rate='10/h', method='POST', block=True)
def student_signin(request):
    sent = False
    if request.method == 'POST':
        ops.request_signin(request.POST.get('identifier', ''))
        sent = True                                        # same answer whether or not anyone matched
    return render(request, 'courses/student_signin.html', {'sent': sent})


@ratelimit(key='ip', rate='30/h', method='GET', block=True)
def student_signin_confirm(request, token):
    email = ops.redeem_signin(token)
    if not email:
        messages.error(request, gettext('That link has expired or was already used. Ask for a new one.'))
        return redirect('student_signin')
    request.session[PORTAL_SESSION_KEY] = email
    request.session.set_expiry(60 * 60 * 8)
    return redirect('student_portal')


def student_portal(request):
    email = request.session.get(PORTAL_SESSION_KEY)
    if not email:
        return redirect('student_signin')
    rows = []
    for reg in ops.registrations_for_email(email):
        pct = ops.attendance_percent(reg)
        rows.append({'reg': reg, 'pct': pct, 'fees': ops.fee_summary(reg),
                     'cert': Certificate.objects.filter(registration=reg).first(),
                     'materials': ops.materials_for(reg).count()})
    return render(request, 'courses/student_portal.html', {'email': email, 'rows': rows})


@require_POST
def student_signout(request):
    request.session.pop(PORTAL_SESSION_KEY, None)
    return redirect('student_signin')
