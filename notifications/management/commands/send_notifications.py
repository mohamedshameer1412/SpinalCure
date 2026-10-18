"""
Run every 15 minutes from cron, e.g.
  */15 * * * * cd /srv/spinalcure && python manage.py send_notifications
Idempotent: every message has a dedupe key, so overlapping or repeated runs send nothing twice.
"""
from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from appointments.notify import flag_missed, send_reminder
from notifications.services import notify_users, retry_failed, users_with_perm


class Command(BaseCommand):
    help = 'Send appointment reminders, flag missed appointments and follow-ups, retry failed emails.'

    def handle(self, *args, **opts):
        now = timezone.localtime()
        tz = now.tzinfo
        hours = getattr(settings, 'APPOINTMENT_REMINDER_HOURS', 24)
        active = ('scheduled', 'confirmed')

        reminders = 0
        upcoming = Appointment.objects.filter(
            status__in=active, email_reminder_sent=False,
            appointment_date__range=(now.date(), (now + timedelta(hours=hours)).date()),
        ).select_related('patient', 'practitioner')
        for a in upcoming:
            start = datetime.combine(a.appointment_date, a.appointment_time, tz)
            if now < start <= now + timedelta(hours=hours):
                send_reminder(a)
                Appointment.objects.filter(pk=a.pk).update(email_reminder_sent=True)
                reminders += 1

        missed = 0
        for a in Appointment.objects.filter(status__in=active, appointment_date__range=(now.date() - timedelta(days=7), now.date())):
            end = datetime.combine(a.appointment_date, a.appointment_time, tz) + timedelta(minutes=a.duration_minutes)
            if end + timedelta(hours=1) < now:
                flag_missed(a)
                missed += 1

        followups = 0
        from patients.models import Session
        due = Session.objects.filter(next_appointment_date__range=(now.date(), now.date() + timedelta(days=1))).select_related('patient')
        staff = users_with_perm('appointments_manage') if due.exists() else []
        for s in due:
            booked = Appointment.objects.filter(patient=s.patient, appointment_date__gte=now.date(), status__in=active).exists()
            if not booked:
                notify_users(staff, 'followup_due', f'Follow-up due: {s.patient.name}',
                             f'Planned for {s.next_appointment_date:%d %b %Y}; no appointment booked yet.',
                             reverse('appointment_calendar'), dedupe_key=f'followup:{s.pk}', email=False)
                followups += 1

        event_reminders = 0
        from events.models import EventRegistration
        from notifications.services import queue_email
        regs = EventRegistration.objects.filter(
            status='confirmed', event__is_published=True, event__is_cancelled=False,
            event__date__range=(now.date(), (now + timedelta(hours=hours)).date()),
        ).exclude(email='').select_related('event')
        for r in regs:
            e = r.event
            if now < e.starts_at <= now + timedelta(hours=hours):
                link = f'{settings.SITE_URL}{reverse("event_registration_manage", args=[r.access_token])}'
                queue_email(r.email, 'event_registration', f'Reminder: {e.title}',
                            f'"{e.title}" starts {e.starts_at:%a %d %b, %I:%M %p} IST.\n'
                            f'{"Join from your registration page: " if e.is_online else "Venue: " + e.venue + chr(10) + "Your registration: "}{link}',
                            dedupe_key=f'evremind:{r.pk}:{e.date}:{e.start_time}')
                event_reminders += 1

        retried = retry_failed()
        self.stdout.write(f'reminders={reminders} event_reminders={event_reminders} missed_flagged={missed} '
                          f'followups={followups} emails_retried_ok={retried}')
