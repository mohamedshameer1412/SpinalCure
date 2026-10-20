from django import template
from django.conf import settings

register = template.Library()


@register.simple_tag
def email_brand():
    """Clinic details + absolute URLs for e-mail templates (rendered without a request)."""
    from clinic.models import ClinicProfile
    clinic = ClinicProfile.objects.first()
    site = settings.SITE_URL.rstrip('/')
    logo = ''
    if clinic and clinic.logo:
        try:
            logo = site + clinic.logo.url
        except Exception:
            logo = ''
    return {
        'clinic': clinic,
        'name': clinic.name if clinic else 'Spinal Cure',
        'tagline': clinic.tagline if clinic else '',
        'logo': logo,
        'site': site,
        'phones': clinic.phone_list if clinic else [],
        'email': clinic.email if clinic else '',
        'address': clinic.address if clinic else '',
        'hours': clinic.working_hours if clinic else '',
        'instagram': clinic.instagram if clinic else '',
        'youtube': clinic.youtube if clinic else '',
    }
