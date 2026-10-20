"""Language choices for model fields, labelled in their own script (English, தமிழ், हिन्दी, తెలుగు, മലയാളം, ಕನ್ನಡ)."""
from django.conf import settings
from django.utils.translation import get_language_info

NATIVE_CHOICES = [(code, get_language_info(code)['name_local']) for code, _name in settings.LANGUAGES]
