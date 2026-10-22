"""
Appointment reminders, treatment follow-ups and missed-appointment handling.

Run every 5-10 minutes from cron:   */5 * * * *  python manage.py send_reminders

Safe to run repeatedly or concurrently: each message carries a dedupe key, so a given reminder is
created at most once per appointment/offset no matter how often this runs.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from appointments import scheduling as sch
from appointments.models import Appointment, BookingSettings
from notifications.service import notify, notify_staff


class Command(BaseCommand):
    help = 'Send appointment reminders, treatment follow-ups and handle missed appointments.'

    def handle(self, *args, **options):
        cfg, now = BookingSettings.get(), timezone.now()
        counts = {'reminders': self.reminders(cfg, now), 'followups': self.followups(cfg, now),
                  'missed': self.missed(cfg, now), 'event_reminders': self.event_reminders(now),
                  'review_requests': self.review_requests(cfg, now), 'course_notices': self.course_notices(now)}
        self.stdout.write(', '.join(f'{k}={v}' for k, v in counts.items()))

    # reminders ---------------------------------------------------------------------------------
    def reminders(self, cfg, now):
        sent = 0
        horizon = now + timedelta(minutes=max(cfg.reminder_offsets or [0]) + 1)
        upcoming = Appointment.objects.filter(
            status__in=('scheduled', 'confirmed'), appointment_date__gte=timezone.localdate(now),
            appointment_date__lte=timezone.localdate(horizon)).select_related('patient', 'practitioner')
        for appt in upcoming:
            start = appt.starts_at
            if start <= now:
                continue
            for offset in cfg.reminder_offsets:
                due_at = start - timedelta(minutes=offset)
                if due_at > now:
                    continue                              # not due yet
                if appt.created_at and appt.created_at > due_at:
                    continue                              # booked after this reminder's moment: no point
                rcpt = sch._recipient(appt)
                if not (rcpt.get('patient') or rcpt.get('email')):
                    continue
                key = f'appt:{appt.pk}:rem:{offset}'
                n = notify('appointment_reminder', context=sch._ctx(appt), url=sch._manage_path(appt),
                           dedupe_key=key, **rcpt)
                if n is not None and getattr(n, 'was_created', False):
                    sent += 1
        return sent

    # follow-ups --------------------------------------------------------------------------------
    def followups(self, cfg, now):
        from patients.models import Session
        today = timezone.localdate()
        sent = 0
        due = Session.objects.filter(
            next_appointment_date__gte=today,
            next_appointment_date__lte=today + timedelta(days=cfg.followup_lead_days)
        ).select_related('patient')
        for session in due:
            booked = Appointment.objects.filter(
                patient=session.patient, status__in=('scheduled', 'confirmed'), appointment_date__gte=today).exists()
            if booked:
                continue
            n = notify('treatment_followup', patient=session.patient, context={'clinic': sch._clinic_name()},
                       dedupe_key=f'followup:{session.pk}')
            if n is not None and getattr(n, 'was_created', False):
                sent += 1
        return sent

    # review requests ---------------------------------------------------------------------------
    def review_requests(self, cfg, now):
        """Once per patient, the day after they reach N sessions: a thank-you with a link to review us.
        Only patients treated in the last 30 days, so switching this on never emails old patients."""
        n = cfg.review_request_after_sessions
        if not n:
            return 0
        from django.db.models import Count, Max
        from patients.models import Patient, Session
        today = timezone.localdate()
        rows = (Session.objects.values('patient').annotate(n=Count('id'), last=Max('session_date'))
                .filter(n__gte=n, last__lt=today, last__gte=today - timedelta(days=30)))
        sent = 0
        for p in Patient.objects.filter(pk__in=[r['patient'] for r in rows]):
            note = notify('review_request', patient=p, context={'clinic': sch._clinic_name()},
                          url=reverse('clinic_review'), dedupe_key=f'review_request:{p.pk}')
            if note is not None and getattr(note, 'was_created', False):
                sent += 1
        return sent

    # missed ------------------------------------------------------------------------------------
    def missed(self, cfg, now):
        handled = 0
        cutoff = now - timedelta(minutes=cfg.missed_grace_minutes)
        stale = Appointment.objects.filter(
            status__in=('scheduled', 'confirmed'), appointment_date__lte=timezone.localdate(now)
        ).select_related('patient', 'practitioner')
        for appt in stale:
            if appt.ends_at > cutoff:
                continue
            if cfg.auto_mark_no_show:
                try:
                    sch.mark_no_show(appt)
                    handled += 1
                except sch.SchedulingError:
                    continue
            else:
                made = notify_staff('appointment_missed_staff', 'appointments.manage', context=sch._ctx(appt),
                                    url=reverse('appointment_calendar'), dedupe_key=f'appt:{appt.pk}:missed_staff')
                if any(getattr(n, 'was_created', False) for n in made):
                    handled += 1
        return handled

    # events ------------------------------------------------------------------------------------
    def event_reminders(self, now):
        from events import service as event_service
        from events.models import Event
        sent = 0
        soon = Event.objects.filter(status='published', date__gte=timezone.localdate(now) - timedelta(days=1),
                                    date__lte=timezone.localdate(now) + timedelta(days=8))
        for event in soon:
            start = event.starts_at
            if start <= now:
                continue
            for offset in event.reminder_offsets:
                due_at = start - timedelta(minutes=offset)
                if due_at > now:
                    continue
                for reg in event.registrations.filter(status='confirmed').exclude(email=''):
                    if reg.registered_at > due_at:
                        continue                      # registered after this reminder's moment
                    if event_service._notify_reg('event_reminder', reg, key_suffix=f':{offset}'):
                        sent += 1
        return sent

    # courses -----------------------------------------------------------------------------------
    def course_notices(self, now):
        """Start-of-batch reminders, one nudge for students who have not added their details, and (once a batch has
        ended) opening feedback and emailing each student their link. Every message has a dedupe key."""
        from courses import service as course_service
        from courses.models import CourseBatch, CourseRegistration
        today, sent = timezone.localdate(now), 0
        starting = CourseBatch.objects.filter(start_date=today + timedelta(days=1), is_published=True)
        for reg in CourseRegistration.objects.filter(batch__in=starting, status='confirmed').select_related('batch__course', 'student'):
            if course_service._notify('course_batch_reminder', reg):
                sent += 1
        cutoff = now - timedelta(days=2)
        pending = CourseRegistration.objects.filter(status='confirmed', registered_at__lte=cutoff, batch__end_date__isnull=True,
                                                    student__profile_completed_at__isnull=True) |             CourseRegistration.objects.filter(status='confirmed', registered_at__lte=cutoff, batch__end_date__gte=today,
                                              student__profile_completed_at__isnull=True)
        for reg in pending.select_related('batch__course', 'student'):
            if course_service._notify('course_profile_request', reg, key=':reminder'):
                sent += 1
        for batch in CourseBatch.objects.filter(end_date__lt=today, end_date__gte=today - timedelta(days=30), is_published=True, registrations__status='confirmed',
                                                registrations__completed_at__isnull=True).distinct():
            sent += course_service.request_feedback(batch)
        return sent

