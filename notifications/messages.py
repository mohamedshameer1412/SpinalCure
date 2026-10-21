"""
Translatable message catalogue. Messages must stay free of clinical detail
(no diagnoses, complaints or treatment notes): they appear in email previews and lock screens.
Placeholders use %(name)s so translators can reorder them.
"""
from datetime import date, datetime, time

from django.utils import translation
from django.utils.formats import date_format, time_format
from django.utils.translation import gettext_noop as N_

# event -> (title msgid, body msgid)
CATALOGUE = {
    'appointment_booked': (
        N_('Appointment booked'),
        N_('Your appointment with %(practitioner)s at %(clinic)s is booked for %(date)s at %(time)s.')),
    'appointment_booked_staff': (
        N_('New appointment: %(who)s'),
        N_('%(who)s booked %(date)s at %(time)s with %(practitioner)s.')),
    'appointment_booked_clinic': (
        N_('New appointment: %(who)s'),
        N_('%(who)s booked %(date)s at %(time)s with %(practitioner)s.')),
    'appointment_confirmed': (
        N_('Appointment confirmed'),
        N_('Your appointment on %(date)s at %(time)s with %(practitioner)s is confirmed.')),
    'appointment_rescheduled': (
        N_('Appointment rescheduled'),
        N_('Your appointment has moved to %(date)s at %(time)s with %(practitioner)s.')),
    'appointment_cancelled': (
        N_('Appointment cancelled'),
        N_('Your appointment on %(date)s at %(time)s has been cancelled. Contact %(clinic)s to rebook.')),
    'appointment_reminder': (
        N_('Appointment reminder'),
        N_('Reminder: you have an appointment on %(date)s at %(time)s with %(practitioner)s at %(clinic)s.')),
    'appointment_missed': (
        N_('We missed you'),
        N_('You did not attend your appointment on %(date)s at %(time)s. Contact %(clinic)s to rebook.')),
    'appointment_missed_staff': (
        N_('Appointment not completed: %(who)s'),
        N_('The appointment for %(who)s on %(date)s at %(time)s was not marked completed or cancelled.')),
    'treatment_followup': (
        N_('Treatment follow-up due'),
        N_('It is time for your follow-up visit. Please book a slot with %(clinic)s.')),
    'review_request': (
        N_('How is your recovery going?'),
        N_('Thank you for choosing %(clinic)s. If our treatment has helped you, a short review helps other '
           'people living with the same pain find us. It takes less than a minute.')),
    'payment_received': (
        N_('Payment received'),
        N_('We received your payment of %(amount)s (receipt %(receipt)s). Thank you.')),
    'payment_failed': (
        N_('Payment failed'),
        N_('A payment of %(amount)s for %(who)s did not go through and needs attention.')),
    'online_payment_received': (
        N_('Online payment received: %(who)s'),
        N_('%(who)s paid %(amount)s online (receipt %(receipt)s).')),
    'invoice_created': (
        N_('Invoice %(invoice)s'),
        N_('An invoice for %(amount)s has been created.')),
    'outstanding_payment': (
        N_('Outstanding payment: %(who)s'),
        N_('%(who)s has %(amount)s outstanding on invoice %(invoice)s.')),
    'staff_invitation': (
        N_('You have been added to %(clinic)s'),
        N_('You were added as %(role)s. Sign in to get started.')),
    'idcard_issued': (
        N_('ID card issued'),
        N_('Your %(card_type)s ID card (%(employee_id)s) has been issued.')),
    'idcard_revoked': (
        N_('ID card revoked'),
        N_('The ID card %(employee_id)s has been revoked and no longer verifies.')),
    'event_registered': (
        N_('Registration confirmed: %(event)s'),
        N_('You are registered for %(event)s on %(date)s at %(time)s.')),
    'event_waitlisted': (
        N_('Waitlisted: %(event)s'),
        N_('%(event)s is full. You are on the waitlist and will be told if a place opens.')),
    'event_promoted': (
        N_('A place opened: %(event)s'),
        N_('A place opened and you are now registered for %(event)s on %(date)s at %(time)s.')),
    'event_changed': (
        N_('Event updated: %(event)s'),
        N_('Details of %(event)s changed. It is now on %(date)s at %(time)s.')),
    'event_cancelled': (
        N_('Event cancelled: %(event)s'),
        N_('%(event)s on %(date)s has been cancelled.')),
    'event_reminder': (
        N_('Starting soon: %(event)s'),
        N_('%(event)s starts on %(date)s at %(time)s.')),
    'course_registered': (
        N_('Registration confirmed: %(event)s'),
        N_('You are registered for %(event)s (%(batch)s), starting %(date)s.')),
    'course_waitlisted': (
        N_('Waitlisted: %(event)s'),
        N_('%(event)s (%(batch)s) is full. You are on the waitlist and will be told if a place opens.')),
    'course_promoted': (
        N_('A place opened: %(event)s'),
        N_('A place opened and you are now registered for %(event)s (%(batch)s), starting %(date)s.')),
    'admin_alert': (
        N_('%(subject)s'),
        N_('%(detail)s')),
}


class _Safe(dict):
    """Missing placeholders render as empty rather than raising mid-notification."""
    def __missing__(self, key):
        return ''


def localise_context(context):
    """Format date/time/datetime values for the active language; leave everything else alone."""
    out = {}
    for key, value in (context or {}).items():
        if isinstance(value, datetime):
            out[key] = date_format(value, 'DATETIME_FORMAT')
        elif isinstance(value, date):
            out[key] = date_format(value, 'DATE_FORMAT')
        elif isinstance(value, time):
            out[key] = time_format(value, 'TIME_FORMAT')
        else:
            out[key] = value
    return out


def render(event_key, context, language):
    """Return (title, body) for the event in `language`."""
    title_id, body_id = CATALOGUE[event_key]
    with translation.override(language):
        ctx = _Safe(localise_context(context))
        return (translation.gettext(title_id) % ctx)[:200], translation.gettext(body_id) % ctx
