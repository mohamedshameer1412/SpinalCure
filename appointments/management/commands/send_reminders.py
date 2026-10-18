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
                  'missed': self.missed(cfg, now), 'event_reminders': self.event_reminders(now)}
        self.stdout.write(', '.join(f'{k}={v}' for k, v in counts.items()))

    # reminders ---------------------------------------------------------------------------------
    def reminders(self, cfg, now):
        sent = 0
        horizon = now + timedelta(minutes=max(cfg.reminder_offsets or [0]) + 1)
        upcoming = Appointment.objects.filter(
            status__in=('scheduled', 'confirmed'), appointment_date__gte=now.date(),
            appointment_date__lte=horizon.date()).select_related('patient', 'practitioner')
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

    # missed ------------------------------------------------------------------------------------
    def missed(self, cfg, now):
        handled = 0
        cutoff = now - timedelta(minutes=cfg.missed_grace_minutes)
        stale = Appointment.objects.filter(
            status__in=('scheduled', 'confirmed'), appointment_date__lte=now.date()
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
        soon = Event.objects.filter(status='published', date__gte=now.date() - timedelta(days=1),
                                    date__lte=now.date() + timedelta(days=8))
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
