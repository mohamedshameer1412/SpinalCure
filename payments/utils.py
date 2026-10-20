from django.utils.translation import gettext
import logging
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from clinic.models import ClinicProfile

logger = logging.getLogger(__name__)

def send_payment_receipt_email(payment, request=None):
    """
    Sends a professional email receipt to the payer.
    Works for patients, students, and participants.
    """
    payer_email = None
    if payment.payer_type == 'patient' and payment.patient:
        payer_email = payment.patient.email
    elif payment.payer_type == 'student' and payment.course_registration:
        payer_email = payment.course_registration.email
    elif payment.payer_type == 'participant' and payment.event_registration:
        payer_email = payment.event_registration.email
    
    # Check manual payer details if linked registrations are missing
    if not payer_email and hasattr(payment, 'manual_payer_email'):
        payer_email = payment.manual_payer_email

    if not payer_email:
        logger.warning(f"No email found for payment {payment.receipt_number}. Skipping email.")
        return False

    clinic = ClinicProfile.objects.first()
    
    subject = gettext('Payment receipt %(no)s — %(clinic)s') % {'no': payment.receipt_number, 'clinic': clinic.name if clinic else 'Spinal Cure'}
    from_email = settings.DEFAULT_FROM_EMAIL
    to = [payer_email]

    # Generate full invoice URL for the email button
    invoice_url = "#"
    if request:
        from django.urls import reverse
        from spinalcure.utils import encode_b64uuid
        invoice_path = reverse('payment_invoice', kwargs={'pk': encode_b64uuid(payment.id)})
        invoice_url = request.build_absolute_uri(invoice_path)

    # Context for template
    context = {
        'payment': payment,
        'clinic': clinic,
        'invoice_url': invoice_url,
    }

    # Render HTML and Plain Text versions
    html_content = render_to_string('payments/emails/receipt_email.html', context)
    text_content = strip_tags(html_content)

    try:
        msg = EmailMultiAlternatives(subject, text_content, from_email, to)
        msg.attach_alternative(html_content, "text/html")
        msg.send()
        logger.info(f"Receipt email sent for {payment.receipt_number} to {payer_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send receipt email for {payment.receipt_number}: {str(e)}")
        return False
