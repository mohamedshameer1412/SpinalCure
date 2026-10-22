"""Course-batch registration rules: capacity, waitlist, duplicates, cancellation. Mirrors events.service."""
from django.utils.translation import gettext
import logging

from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from events.service import EventError, phone_key
from notifications.service import notify

from .models import CourseBatch, CourseRegistration, Student

logger = logging.getLogger(__name__)


def manage_path(reg):
    return reverse('course_registration_manage', args=[reg.access_token])


def _notify(kind, reg, key=''):
    email = reg.email or (reg.student.email if reg.student_id else '')
    if not email:
        return None
    try:
        batch = reg.batch
        n = notify(kind, email=email, url=manage_path(reg), dedupe_key=f'course:{reg.pk}:{kind}{key}',
                   context={'event': batch.course.title, 'batch': batch.name, 'date': batch.start_date, 'name': reg.name})
        return n if n is not None and getattr(n, 'was_created', False) else None
    except Exception:
        logger.exception('Course notification failed')
        return None


def register(batch, *, name, phone, email='', notes=''):
    key = phone_key(phone)
    if len(key) < 7:
        raise EventError('invalid_phone', gettext('Please enter a valid phone number.'))
    with transaction.atomic():
        b = CourseBatch.objects.select_for_update().select_related('course').get(pk=batch.pk)
        if not (b.is_active and b.is_published and b.course.is_published) or b.is_completed:
            raise EventError('closed', gettext('Registration is not open for this course.'))
        dup = Q(phone_key=key) | (Q(email__iexact=email) if email else Q(pk__in=[]))
        if b.registrations.filter(dup, status__in=('confirmed', 'waitlisted')).exists():
            raise EventError('duplicate', gettext('You are already registered for this intake. Check your email for the link.'))
        status = 'waitlisted' if b.is_full else 'confirmed'
        reg = CourseRegistration.objects.create(batch=b, name=name, phone=phone, phone_key=key, email=email,
                                                notes=notes, status=status)
        link_student(reg)
    _notify('course_registered' if status == 'confirmed' else 'course_waitlisted', reg)
    if status == 'confirmed':
        request_profile(reg)
    return reg


def promote_waitlist(batch):
    promoted = []
    with transaction.atomic():
        b = CourseBatch.objects.select_for_update().get(pk=batch.pk)
        for reg in b.registrations.select_for_update().filter(status='waitlisted').order_by('registered_at'):
            if b.is_full:
                break
            reg.status, reg.promoted_at = 'confirmed', timezone.now()
            reg.save(update_fields=['status', 'promoted_at'])
            promoted.append(reg)
    for reg in promoted:
        _notify('course_promoted', reg)
        request_profile(reg)
    return promoted


def cancel_registration(reg, by_staff=False):
    with transaction.atomic():
        b = CourseBatch.objects.select_for_update().get(pk=reg.batch_id)
        reg = CourseRegistration.objects.select_for_update().get(pk=reg.pk)
        if reg.status == 'cancelled':
            return reg
        if not by_staff and b.start_date <= timezone.localdate():
            raise EventError('started', gettext('This batch has already started, so it can no longer be cancelled online.'))
        was_confirmed = reg.status == 'confirmed'
        reg.status, reg.cancelled_at = 'cancelled', timezone.now()
        reg.save(update_fields=['status', 'cancelled_at'])
    if was_confirmed:
        promote_waitlist(b)
    return reg


# ── students: one record per person, completed after the place is confirmed ──────────────────────

def link_student(reg):
    """Give the registration its own Student record. Phone numbers and emails typed on a public form are unverified, so
    they are never used to merge people: otherwise anyone could register with someone else's number or email and use
    their own private link to read or change that person's profile and card. Staff see other records that share a phone
    number on the student page and reconcile them by hand."""
    st = Student.objects.create(name=reg.name, phone=reg.phone, phone_key=reg.phone_key, email=reg.email)
    reg.student = st
    reg.save(update_fields=['student'])
    return st


def request_profile(reg, resend=False):
    """Email the student the link where they add their photo and details (once automatically; again on request)."""
    if reg.status != 'confirmed' or (reg.student_id and reg.student.profile_complete):
        return None
    return _notify('course_profile_request', reg, key=f':{timezone.now().timestamp()}' if resend else '')


def complete_profile(reg):
    """The student has filled in their details: mark it, send the ID card, tell staff."""
    st = reg.student
    st.profile_completed_at = timezone.now()
    st.save(update_fields=['profile_completed_at'])
    for r in st.registrations.filter(status='confirmed').select_related('batch__course'):
        _notify('course_card_ready', r)
    try:
        from notifications.service import notify_staff
        b = reg.batch
        notify_staff('course_profile_completed', 'events.registrations',
                     context={'name': st.name, 'event': b.course.title, 'batch': b.name},
                     url=reverse('student_detail', args=[st.pk]), dedupe_key=f'student:{st.pk}:profile')
    except Exception:
        logger.exception('Staff notification failed')


def request_feedback(batch):
    """Ask every confirmed student of a finished batch for feedback: opens the form and emails each their link."""
    if not batch.feedback_enabled:
        batch.feedback_enabled = True
        batch.save(update_fields=['feedback_enabled'])
    sent = 0
    for reg in batch.registrations.filter(status='confirmed').select_related('batch__course', 'student'):
        if not reg.completed_at:
            reg.completed_at = timezone.now()
            reg.save(update_fields=['completed_at'])
        if not hasattr(reg, 'feedback') and _notify('course_feedback_request', reg):
            sent += 1
    return sent
