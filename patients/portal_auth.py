"""
Patient-portal OTP login.

* Codes are random, short-lived, attempt-limited and stored only as a keyed hash in the
  server-side session.
* Responses never reveal whether a phone number is registered.
* Delivery is by email (SMTP). A patient with no email on file cannot receive a code;
  SMS/WhatsApp delivery needs a configured provider and is intentionally not simulated.
"""
import hashlib
import hmac
import logging
import secrets
import time

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.utils.translation import gettext as _

from spinalcure.blind_index import phone_index
from .models import Patient

logger = logging.getLogger(__name__)

CODE_TTL_SECONDS = 10 * 60
MAX_ATTEMPTS = 5
PER_PHONE_PER_HOUR = 3
PER_IP_PER_HOUR = 10

SESSION_KEY = 'portal_otp'


def _digest(code, index):
    key = hashlib.sha256(b'portal-otp:' + settings.SECRET_KEY.encode()).digest()
    return hmac.new(key, f'{index}:{code}'.encode(), hashlib.sha256).hexdigest()


def _client_ip(request):
    return request.META.get('REMOTE_ADDR', 'unknown')


def _hit(key, limit):
    """Increment a one-hour counter; return True while still under the limit."""
    cache.add(key, 0, timeout=3600)
    try:
        return cache.incr(key) <= limit
    except ValueError:  # key expired between add and incr
        cache.set(key, 1, timeout=3600)
        return True


def request_code(request, phone):
    """
    Start a login attempt. Always returns True/False for "throttled?" only; callers must show
    the same message regardless of whether the patient exists or a mail was actually sent.
    Returns False when throttled.
    """
    index = phone_index(phone)
    if not index:
        return True
    if not _hit(f'portal_otp_ip:{_client_ip(request)}', PER_IP_PER_HOUR):
        return False
    if not _hit(f'portal_otp_phone:{index}', PER_PHONE_PER_HOUR):
        return False

    code = f'{secrets.randbelow(10 ** 6):06d}'
    # Store state even for unknown numbers so the verify step behaves identically.
    request.session[SESSION_KEY] = {
        'index': index,
        'digest': _digest(code, index),
        'expires': time.time() + CODE_TTL_SECONDS,
        'attempts': 0,
    }

    patient = Patient.objects.filter(phone_index=index).first()
    if patient and patient.email:
        try:
            send_mail(
                subject=_('%(site)s patient portal sign-in code') % {'site': settings.SITE_NAME},
                message=_('Your sign-in code is %(code)s. It expires in %(m)d minutes. '
                          'If you did not request it, ignore this email.') % {'code': code, 'm': CODE_TTL_SECONDS // 60},
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[patient.email],
                fail_silently=False,
            )
        except Exception:
            logger.exception('Portal OTP email failed for patient %s', patient.pk)
    elif patient:
        logger.warning('Portal OTP requested for patient %s who has no email on file', patient.pk)
    return True


def pending_login(request):
    state = request.session.get(SESSION_KEY)
    return bool(state and state['expires'] > time.time())


def verify_code(request, code):
    """Return the Patient on success, else None. Consumes the challenge on success or lock-out."""
    state = request.session.get(SESSION_KEY)
    if not state or state['expires'] <= time.time():
        request.session.pop(SESSION_KEY, None)
        return None

    state['attempts'] += 1
    request.session[SESSION_KEY] = state
    if state['attempts'] > MAX_ATTEMPTS:
        request.session.pop(SESSION_KEY, None)
        return None

    if not hmac.compare_digest(_digest((code or '').strip(), state['index']), state['digest']):
        return None

    patient = Patient.objects.filter(phone_index=state['index']).first()
    request.session.pop(SESSION_KEY, None)
    if not patient:
        return None
    request.session.cycle_key()  # new session id on privilege change (fixation defence)
    request.session['patient_id'] = str(patient.id)
    return patient
