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
            
    return {
        'clinic': clinic,
        'clinic_info': clinic,
        'clinic_logo_url': clinic_logo_url,
    }
