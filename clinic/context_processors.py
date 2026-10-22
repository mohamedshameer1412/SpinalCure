from django.utils.functional import SimpleLazyObject

from clinic import hours
from clinic.models import ClinicProfile

def clinic_info(request):
    """
    Makes clinic profile information available in all templates under both
    'clinic' and 'clinic_info' for consistency and backward compatibility.
    Also passes 'clinic_logo_url' as a direct string for reliable navbar rendering.
    """
    clinic = ClinicProfile.objects.first()
    clinic_logo_url = None
    if clinic and clinic.logo:
        try:
            clinic_logo_url = clinic.logo.url
        except Exception:
            clinic_logo_url = None
            
    # optional variant for dark backgrounds, stored next to the logo as <name>_on_dark.<ext>
    clinic_logo_dark_url = clinic_logo_url
    if clinic_logo_url:
        try:
            import os
            stem, ext = os.path.splitext(clinic.logo.name)
            if clinic.logo.storage.exists(f'{stem}_on_dark{ext}'):
                clinic_logo_dark_url = clinic.logo.storage.url(f'{stem}_on_dark{ext}')
        except Exception:
            pass
    return {
        'clinic_logo_dark_url': clinic_logo_dark_url,
        'clinic': clinic,
        'clinic_info': clinic,
        'clinic_logo_url': clinic_logo_url,
        'clinic_hours_text': SimpleLazyObject(lambda: hours.opening_hours(clinic)),
        'clinic_map_url': SimpleLazyObject(lambda: hours.map_url(clinic)),
    }
