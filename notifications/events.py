"""
Registry of notification events.

audience  'staff'   -> clinic users (in-app + email)
          'patient' -> patients / guests (email, plus SMS/WhatsApp when a provider is configured)
persistent: stays visible as an alert until resolved (actionable / unresolved problems)
default_channels: used when the recipient has not set a preference for the event.
Message text lives in notifications/messages.py so it can be translated.
"""
from dataclasses import dataclass, field

IN_APP, EMAIL, SMS, WHATSAPP, BROWSER = 'in_app', 'email', 'sms', 'whatsapp', 'browser'
CHANNELS = [IN_APP, EMAIL, SMS, WHATSAPP, BROWSER]
EXTERNAL_CHANNELS = [EMAIL, SMS, WHATSAPP]


@dataclass(frozen=True)
class EventSpec:
    key: str
    label: str
    audience: str
    level: str = 'info'
    persistent: bool = False
    default_channels: tuple = (IN_APP, EMAIL)
    configurable: bool = True


_EVENTS = [
    EventSpec('appointment_booked', 'Appointment booked', 'patient', 'success'),
    EventSpec('appointment_booked_staff', 'New appointment booked', 'staff', 'info', default_channels=(IN_APP,)),
    EventSpec('appointment_booked_clinic', 'New appointment (clinic inbox)', 'staff', 'info',
              default_channels=(EMAIL,), configurable=False),
    EventSpec('appointment_confirmed', 'Appointment confirmed', 'patient', 'success'),
    EventSpec('appointment_rescheduled', 'Appointment rescheduled', 'patient', 'warning'),
    EventSpec('appointment_cancelled', 'Appointment cancelled', 'patient', 'warning'),
    EventSpec('appointment_reminder', 'Appointment reminder', 'patient', 'info', default_channels=(IN_APP, EMAIL, SMS)),
    EventSpec('appointment_missed', 'Missed appointment', 'patient', 'warning'),
    EventSpec('appointment_missed_staff', 'Appointment not completed', 'staff', 'warning', True, (IN_APP,)),
    EventSpec('treatment_followup', 'Treatment follow-up due', 'patient', 'info'),
    EventSpec('payment_received', 'Payment received', 'patient', 'success'),
    EventSpec('review_request', 'How was your treatment?', 'patient', 'info', default_channels=(IN_APP, EMAIL)),
    EventSpec('payment_failed', 'Payment failed', 'staff', 'danger', True, (IN_APP, EMAIL)),
    EventSpec('online_payment_received', 'Online payment received', 'staff', 'success', default_channels=(IN_APP,)),
    EventSpec('invoice_created', 'Invoice created', 'patient', 'info'),
    EventSpec('outstanding_payment', 'Outstanding payment', 'staff', 'warning', True, (IN_APP,)),
    EventSpec('staff_invitation', 'Staff invitation', 'staff', 'info', configurable=False,
              default_channels=(IN_APP, EMAIL)),
    EventSpec('idcard_issued', 'ID card issued', 'staff', 'success'),
    EventSpec('idcard_revoked', 'ID card revoked', 'staff', 'danger', True, configurable=False),
    EventSpec('event_registered', 'Event registration confirmed', 'patient', 'success'),
    EventSpec('event_waitlisted', 'Added to event waitlist', 'patient', 'info'),
    EventSpec('event_promoted', 'Waitlist spot available', 'patient', 'success'),
    EventSpec('event_changed', 'Event details changed', 'patient', 'warning'),
    EventSpec('event_cancelled', 'Event cancelled', 'patient', 'danger'),
    EventSpec('event_reminder', 'Event reminder', 'patient', 'info', default_channels=(IN_APP, EMAIL)),
    EventSpec('course_registered', 'Course registration confirmed', 'patient', 'success'),
    EventSpec('course_waitlisted', 'Added to course waitlist', 'patient', 'info'),
    EventSpec('course_promoted', 'Course place available', 'patient', 'success'),
    EventSpec('course_profile_request', 'Complete your course registration', 'patient', 'info'),
    EventSpec('course_card_ready', 'Student ID card ready', 'patient', 'success'),
    EventSpec('course_feedback_request', 'Course feedback request', 'patient', 'info'),
    EventSpec('course_batch_reminder', 'Course starting soon', 'patient', 'info'),
    EventSpec('course_certificate', 'Course certificate', 'patient', 'success'),
    EventSpec('course_profile_completed', 'Student profile completed', 'staff', 'success', default_channels=(IN_APP,)),
    EventSpec('admin_alert', 'Administrative alert', 'staff', 'danger', True, (IN_APP, EMAIL)),
]
EVENTS = {e.key: e for e in _EVENTS}
EVENT_CHOICES = [(e.key, e.label) for e in _EVENTS]
LEVELS = ['info', 'success', 'warning', 'danger']


def get_event(key):
    try:
        return EVENTS[key]
    except KeyError:
        raise ValueError(f'Unknown notification event: {key}')
