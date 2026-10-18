"""Context for the HTML card component and absolute URLs used in QR codes."""
import base64
import io

from django.conf import settings
from django.urls import reverse

from . import render
from .models import IDCardBranding


def verify_url(card):
    """Absolute, language-independent URL printed in the front QR. Uses SITE_URL, never the request host."""
    return settings.SITE_URL.rstrip('/') + reverse('idcard_verify', args=[card.card_id])


def org_url(card, data=None):
    from clinic.models import ClinicProfile
    brand = IDCardBranding.get()
    clinic = ClinicProfile.objects.first()
    return brand.org_url or (clinic.website if clinic and clinic.website else '') or verify_url(card)


def _qr_data_uri(data, size=480):
    out = io.BytesIO()
    render.qr_image(data, size).save(out, 'PNG')
    return 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode()


def card_context(card, lang, public=False):
    d = render.card_data(card, lang, public)
    d['qr_front'] = _qr_data_uri(verify_url(card))
    d['qr_back'] = _qr_data_uri(org_url(card))
    d['verify_url'] = verify_url(card)
    d['photo_url'] = card.holder.user.photo.url if d['photo'] else ''
    d['logo_url'] = ''
    from clinic.models import ClinicProfile
    c = ClinicProfile.objects.first()
    if d['logo'] and c and c.logo:
        d['logo_url'] = c.logo.url
    d['card'] = card
    return d
