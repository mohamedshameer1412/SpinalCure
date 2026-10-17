"""
Clinic Email Utilities
Handles sending transactional emails for clinic operations.
"""
import logging
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def send_booking_confirmation_email(appointment, request=None):
    """
    Send an appointment booking confirmation email to the patient (if email provided)
    and a notification to the clinic admin.

    Args:
        appointment: Appointment model instance
        request: optional HttpRequest for building absolute URLs
    """
    clinic = None
    try:
        from clinic.models import ClinicProfile
        clinic = ClinicProfile.objects.first()
    except Exception:
        pass

    clinic_name = clinic.name if clinic else "SpinalCure Clinic"
    clinic_address = clinic.address if clinic else ""
    clinic_phone = clinic.phone if clinic else ""
    clinic_email = clinic.email if clinic else settings.DEFAULT_FROM_EMAIL
    admin_email = clinic_email or settings.DEFAULT_FROM_EMAIL

    practitioner_name = "Any Available Doctor"
    specialization = ""
    if appointment.practitioner:
        practitioner_name = str(appointment.practitioner)
        specialization = appointment.practitioner.specialization or ""

    booking_ref = str(appointment.id)[:8].upper()

    import urllib.parse
    from datetime import datetime, timedelta, date, time

    app_date = appointment.appointment_date
    app_time = appointment.appointment_time

    if isinstance(app_date, str):
        app_date = datetime.strptime(app_date, '%Y-%m-%d').date()
    if isinstance(app_time, str):
        app_time_str = app_time[:5]  # Support both 'HH:MM' and 'HH:MM:SS'
        app_time = datetime.strptime(app_time_str, '%H:%M').time()

    start_dt = datetime.combine(app_date, app_time)
    end_dt = start_dt + timedelta(minutes=appointment.duration_minutes)
    
    start_str = start_dt.strftime('%Y%m%dT%H%M%S')
    end_str = end_dt.strftime('%Y%m%dT%H%M%S')
    
    p_name = appointment.patient.name if appointment.patient else appointment.guest_name
    p_phone = appointment.patient.phone if appointment.patient else appointment.guest_phone
    
    details_text = f"Patient: {p_name}\nPhone: {p_phone}\nReason: {appointment.reason or 'N/A'}"
    google_calendar_url = f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={urllib.parse.quote('Appointment: ' + p_name)}&dates={start_str}/{end_str}&details={urllib.parse.quote(details_text)}&location={urllib.parse.quote(clinic_address)}&ctz=Asia/Kolkata"

    import uuid
    uid_str = str(uuid.uuid4())
    now_str = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')

    ics_content = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//SpinalCure//SpinalCure Clinic//EN\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:REQUEST\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid_str}\r\n"
        f"DTSTAMP:{now_str}\r\n"
        f"SUMMARY:Appointment with {clinic_name}\r\n"
        f"DTSTART;TZID=Asia/Kolkata:{start_str}\r\n"
        f"DTEND;TZID=Asia/Kolkata:{end_str}\r\n"
        f"LOCATION:{clinic_address}\r\n"
        f"DESCRIPTION:Patient: {p_name}\\nPhone: {p_phone}\\nReason: {appointment.reason or 'N/A'}\\nPractitioner: {practitioner_name}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )

    context = {
        "patient_name": p_name,
        "appointment_date": app_date,
        "appointment_time": app_time.strftime("%I:%M %p"),
        "practitioner_name": practitioner_name,
        "specialization": specialization,
        "clinic_address": clinic_address,
        "clinic_name": clinic_name,
        "clinic_phone": clinic_phone,
        "booking_reference": booking_ref,
        "reason": appointment.reason or "",
        "google_calendar_url": google_calendar_url,
    }

    subject = f"Appointment Confirmed — {clinic_name}"
    html_content = render_to_string("emails/booking_confirmation.html", context)
    text_content = strip_tags(html_content)
    from_email = settings.DEFAULT_FROM_EMAIL

    # --- 1. Send to patient (if they have an email) ---
    patient_email = appointment.patient.email if appointment.patient else appointment.guest_email
    if patient_email:
        try:
            msg = EmailMultiAlternatives(subject, text_content, from_email, [patient_email])
            msg.attach_alternative(html_content, "text/html")
            msg.attach('invite.ics', ics_content, 'text/calendar')
            msg.send(fail_silently=False)
            logger.info(
                f"Booking confirmation email sent to patient {p_name} "
                f"<{patient_email}> for appointment {booking_ref}"
            )
        except Exception as e:
            logger.error(f"Failed to send booking confirmation to patient {patient_email}: {e}")

    # --- 2. Notify clinic admin ---
    try:
        admin_subject = f"[New Booking] {p_name} - {appointment.appointment_date}"
        admin_html = render_to_string("emails/admin_booking_notify.html", {
            **context,
            "admin_notification": True,
        })
        admin_text = strip_tags(admin_html)
        
        # Build recipients list (clinic admin + doctor if assigned)
        recipients = [admin_email]
        if appointment.practitioner and appointment.practitioner.email:
            recipients.append(appointment.practitioner.email)
            
        msg_admin = EmailMultiAlternatives(admin_subject, admin_text, from_email, recipients)
        msg_admin.attach_alternative(admin_html, "text/html")
        msg_admin.attach('invite.ics', ics_content, 'text/calendar')
        msg_admin.send(fail_silently=True)
        logger.info(f"Admin booking notification sent to {admin_email}")
    except Exception as e:
        logger.error(f"Failed to send admin booking notification: {e}")
