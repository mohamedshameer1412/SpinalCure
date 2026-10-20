"""Language choices for model fields, labelled in their own script (English, தமிழ், हिन्दी, తెలుగు, മലയാളം, ಕನ್ನಡ).
Labels are fixed here rather than read from Django's locale data, which differs between Django releases and would
otherwise make migrations depend on the installed version."""
from django.conf import settings

NATIVE_NAMES = {'en': 'English', 'ta': 'தமிழ்', 'hi': 'हिन्दी', 'te': 'తెలుగు', 'ml': 'മലയാളം', 'kn': 'ಕನ್ನಡ'}
NATIVE_CHOICES = [(code, NATIVE_NAMES.get(code, name)) for code, name in settings.LANGUAGES]


def fix_language_info():
    """Make {% get_language_info %} (the language switcher) use the same native labels."""
    from django.conf.locale import LANG_INFO
    for code, name in NATIVE_NAMES.items():
        if code in LANG_INFO:
            LANG_INFO[code]['name_local'] = name
