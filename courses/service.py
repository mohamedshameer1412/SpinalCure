"""Course-batch registration rules: capacity, waitlist, duplicates, cancellation. Mirrors events.service."""
from django.utils.translation import gettext
import logging

from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from events.service import EventError, phone_key
from notifications.service import notify

from .models import CourseBatch, CourseRegistration

logger = logging.getLogger(__name__)


def manage_path(reg):
    return reverse('course_registration_manage', args=[reg.access_token])


def _notify(kind, reg):
    if not reg.email:
        return None
    try:
        batch = reg.batch
        n = notify(kind, email=reg.email, url=manage_path(reg), dedupe_key=f'course:{reg.pk}:{kind}',
                   context={'event': batch.course.title, 'batch': batch.name, 'date': batch.start_date})
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
    _notify('course_registered' if status == 'confirmed' else 'course_waitlisted', reg)
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
