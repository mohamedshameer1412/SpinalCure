"""
Delivery channels. Email goes through Django's configured SMTP backend.

SMS / WhatsApp are only sent through a provider the operator configures:
    NOTIFY_SMS_BACKEND = 'dotted.path.to.SmsBackend'
    NOTIFY_WHATSAPP_BACKEND = 'dotted.path.to.WhatsAppBackend'
A backend is any class with `send(to, text) -> str|None` that raises on failure.
With none configured those channels are marked "skipped" - never "sent".
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import translation
from django.utils.html import strip_tags
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


class ChannelNotConfigured(Exception):
    pass


class RecipientUnavailable(Exception):
    """No address on file for this channel; retrying will not help."""


def send_email(notification, to):
    from clinic.models import ClinicProfile
    clinic = ClinicProfile.objects.first()
    with translation.override(notification.language):
        html = render_to_string('notifications/email.html', {
            'notification': notification,
            'clinic': clinic,
            'site_url': settings.SITE_URL,
            'link': (settings.SITE_URL.rstrip('/') + notification.url) if notification.url else '',
        })
    msg = EmailMultiAlternatives(
        subject=notification.title,
        body=strip_tags(notification.body) + (f'\n\n{settings.SITE_URL.rstrip("/")}{notification.url}' if notification.url else ''),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to],
    )
    msg.attach_alternative(html, 'text/html')
    msg.send(fail_silently=False)
    return None


def _provider(setting_name):
    path = getattr(settings, setting_name, '')
    if not path:
        raise ChannelNotConfigured(f'{setting_name} is not set')
    return import_string(path)()


def send_sms(notification, to):
    return _provider('NOTIFY_SMS_BACKEND').send(to, f'{notification.title}: {notification.body}')


def send_whatsapp(notification, to):
    return _provider('NOTIFY_WHATSAPP_BACKEND').send(to, f'{notification.title}: {notification.body}')


SENDERS = {'email': send_email, 'sms': send_sms, 'whatsapp': send_whatsapp}
