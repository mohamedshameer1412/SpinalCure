"""Appointment notifications. Patient emails carry only date, time, clinic and practitioner name."""
from django.urls import reverse
from django.utils import formats

from notifications.services import notify_users, queue_email, user_for_practitioner, users_with_perm


def _who(a):
    return a.patient.name if a.patient else (a.guest_name or 'Guest')


def _email_of(a):
    return a.patient.email if a.patient else a.guest_email


def _when(a):
    return f"{formats.date_format(a.appointment_date, 'D, d M Y')} at {a.appointment_time.strftime('%I:%M %p')}"


def _clinic_name():
    from clinic.models import ClinicProfile
    c = ClinicProfile.objects.first()
    return c.name if c else 'SpinalCure'


def _staff_for(a):
    users = users_with_perm('appointments_manage')
    doc = user_for_practitioner(a.practitioner)
    return users + [doc] if doc and doc not in users else users


def appointment_changed(a, event, public=False):
    """event: booked | rescheduled | cancelled | confirmed."""
    url = reverse('appointment_calendar')
    titles = {
        'booked': f'New {"online " if public else ""}booking: {_who(a)}',
        'rescheduled': f'Appointment moved: {_who(a)}',
        'cancelled': f'Appointment cancelled: {_who(a)}',
        'confirmed': f'Appointment confirmed: {_who(a)}',
    }
    # Staff who did it already know; in-app alerts go out for public bookings and for changes.
    if public or event != 'booked':
        notify_users(_staff_for(a), f'appointment_{event}', titles[event], _when(a), url,
                     dedupe_key=f'appt:{a.pk}:{event}:{a.appointment_date}:{a.appointment_time}', email=False)
    if event in ('rescheduled', 'cancelled'):
        clinic = _clinic_name()
        text = {
            'rescheduled': f'Your appointment at {clinic} has been moved to {_when(a)}.',
            'cancelled': f'Your appointment at {clinic} on {_when(a)} has been cancelled. Please call us to book again.',
        }[event]
        queue_email(_email_of(a), f'appointment_{event}', f'{clinic}: appointment {event}', text,
                    dedupe_key=f'appt-mail:{a.pk}:{event}:{a.appointment_date}:{a.appointment_time}')


def send_reminder(a):
    clinic = _clinic_name()
    doc = f' with {a.practitioner.name}' if a.practitioner else ''
    return queue_email(_email_of(a), 'appointment_reminder', f'Reminder: your appointment at {clinic}',
                       f'This is a reminder of your appointment{doc} on {_when(a)} at {clinic}.\n'
                       'If you cannot attend, please call the clinic to reschedule.',
                       dedupe_key=f'reminder:{a.pk}:{a.appointment_date}:{a.appointment_time}')


def flag_missed(a):
    notify_users(users_with_perm('appointments_manage'), 'appointment_missed',
                 f'Outcome needed: {_who(a)}', f'{_when(a)} is past and still marked {a.get_status_display()}.',
                 reverse('appointment_calendar'), dedupe_key=f'missed:{a.pk}', email=False)
