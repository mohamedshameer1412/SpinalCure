"""Course operations: attendance, certificates, fee instalments, study materials and the student sign-in link."""
import hashlib
import logging
import secrets
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone

from notifications.service import notify

from . import service
from .models import Attendance, Certificate, CourseFeePayment, CourseMaterial, StudentLoginToken, Student

logger = logging.getLogger(__name__)
LOGIN_MINUTES = 30


# ── attendance ───────────────────────────────────────────────────────────────────────────────────

def attendance_percent(reg, total=None, present=None):
    """Percent of the batch's sessions the student attended, or None before any session has been held."""
    total = reg.batch.sessions.count() if total is None else total
    if not total:
        return None
    present = reg.attendance.filter(present=True, session__batch_id=reg.batch_id).count() if present is None else present
    return round(100 * present / total)


def eligible(reg, pct=None):
    pct = attendance_percent(reg) if pct is None else pct
    return reg.status == 'confirmed' and pct is not None and pct >= reg.batch.min_attendance_percent


def save_attendance(batch, present_keys):
    """present_keys: set of (session_pk, registration_pk) ticked as present; everything else for confirmed students is absent."""
    sessions = list(batch.sessions.all())
    regs = list(batch.registrations.filter(status='confirmed'))
    existing = {(a.session_id, a.registration_id): a for a in Attendance.objects.filter(session__in=sessions)}
    create, change = [], []
    for s in sessions:
        for r in regs:
            want = (str(s.pk), str(r.pk)) in present_keys
            cur = existing.get((s.pk, r.pk))
            if cur is None:
                create.append(Attendance(session=s, registration=r, present=want))
            elif cur.present != want:
                cur.present = want
                change.append(cur)
    Attendance.objects.bulk_create(create)
    if change:
        Attendance.objects.bulk_update(change, ['present'])
    return len(create) + len(change)


# ── certificates ─────────────────────────────────────────────────────────────────────────────────

def send_certificate(cert, resend=False):
    """Email the certificate PDF (attached by notifications.channels) to the student."""
    reg = cert.registration
    email = reg.email or (reg.student.email if reg.student_id else '')
    if not email:
        return None
    key = f'cert:{cert.code}' + (f':{timezone.now().timestamp()}' if resend else '')
    n = notify('course_certificate', email=email, url=service.manage_path(reg), dedupe_key=key,
               context={'event': reg.batch.course.title, 'batch': reg.batch.name, 'name': reg.name, 'code': cert.code})
    if n is not None and getattr(n, 'was_created', False):
        cert.emailed_at = timezone.now()
        cert.save(update_fields=['emailed_at'])
        return n
    return None


def issue_certificates(batch, send=True):
    """Certificate for every confirmed student who attended enough and has none yet; emails each one. Returns (issued, emailed)."""
    issued = emailed = 0
    total = batch.sessions.count()
    if not total:
        return 0, 0
    for reg in batch.registrations.filter(status='confirmed', certificate__isnull=True).select_related('batch__course', 'student'):
        pct = attendance_percent(reg, total)
        if not eligible(reg, pct):
            continue
        cert = Certificate.objects.create(registration=reg, attendance_percent=pct)
        issued += 1
        if send and send_certificate(cert):
            emailed += 1
    return issued, emailed


# ── fees ─────────────────────────────────────────────────────────────────────────────────────────

def fee_summary(reg):
    """Fee, paid and balance for a registration (uses prefetched payments when available)."""
    fee = reg.fee_override if reg.fee_override is not None else reg.batch.course.fees
    payments = reg.fee_payments.all()
    paid = sum((p.amount for p in payments), Decimal('0'))
    return {'fee': fee, 'paid': paid, 'balance': max(fee - paid, Decimal('0')), 'overpaid': max(paid - fee, Decimal('0')),
            'payments': list(payments)}


# ── study materials ──────────────────────────────────────────────────────────────────────────────

def materials_for(reg):
    if reg.status != 'confirmed':
        return CourseMaterial.objects.none()
    return CourseMaterial.objects.filter(is_published=True, course_id=reg.batch.course_id).filter(
        Q(batch__isnull=True) | Q(batch_id=reg.batch_id))


# ── student sign-in link ─────────────────────────────────────────────────────────────────────────

def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _send_login_email(email, token):
    from django.conf import settings
    from django.core.mail import send_mail
    from django.utils.translation import gettext
    link = settings.SITE_URL.rstrip('/') + reverse('student_signin_confirm', args=[token])
    try:
        send_mail(gettext('Your sign-in link'),
                  gettext('Open this link to see your courses, certificates and study materials. It works once and expires in %(m)s minutes:\n\n%(link)s\n\nIf you did not ask for it, ignore this email.')
                  % {'m': LOGIN_MINUTES, 'link': link},
                  settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
    except Exception:
        logger.exception('Sign-in email failed')


def request_signin(identifier):
    """Email a one-time link to the address ON FILE for whoever matches `identifier` (an email or a phone number).
    Nothing is revealed to the caller either way, and the link only ever goes to a stored address."""
    from events.service import phone_key
    ident = (identifier or '').strip()[:254]
    if '@' in ident:
        emails = {ident.lower()} if Student.objects.filter(email__iexact=ident).exists() else set()
    else:
        key = phone_key(ident)
        emails = ({e.lower() for e in Student.objects.filter(phone_key=key).exclude(email='').values_list('email', flat=True)}
                  if len(key) >= 7 else set())
    for email in emails:
        token = secrets.token_urlsafe(32)
        StudentLoginToken.objects.create(email=email, token_hash=_hash(token),
                                         expires_at=timezone.now() + timedelta(minutes=LOGIN_MINUTES))
        _send_login_email(email, token)
    return len(emails)


def redeem_signin(token):
    """The verified email for a valid, unused, unexpired link (consumed here), else None."""
    row = StudentLoginToken.objects.filter(token_hash=_hash(token or ''), used_at__isnull=True,
                                           expires_at__gt=timezone.now()).first()
    if not row:
        return None
    row.used_at = timezone.now()
    row.save(update_fields=['used_at'])
    return row.email


def registrations_for_email(email):
    from .models import CourseRegistration
    return (CourseRegistration.objects.filter(Q(student__email__iexact=email) | Q(email__iexact=email))
            .select_related('batch__course', 'student').prefetch_related('fee_payments').order_by('-registered_at'))


def merge_students(keep, other):
    """Staff action: fold `other` into `keep` (registrations and notes move; blanks are filled; `other` is removed)."""
    for f in ('email', 'designation', 'organisation', 'address', 'date_of_birth', 'gender', 'blood_group',
              'emergency_contact_name', 'emergency_contact_phone'):
        if not getattr(keep, f) and getattr(other, f):
            setattr(keep, f, getattr(other, f))
    if not keep.photo and other.photo:
        keep.photo = other.photo.name
    if not keep.profile_completed_at and other.profile_completed_at:
        keep.profile_completed_at = other.profile_completed_at
    keep.save()
    other.registrations.update(student=keep)
    other.notes.update(student=keep)
    Student.objects.filter(pk=other.pk).delete()
    return keep
