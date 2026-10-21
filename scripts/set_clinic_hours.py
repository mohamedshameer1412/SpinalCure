"""Set the clinic's weekly hours: Monday-Saturday 10:30 am-1:30 pm and 5:30 pm-8:30 pm, Sunday closed.

    DJANGO_ENV=development python scripts/set_clinic_hours.py

Updates every active practitioner's bookable shifts, the opening-hours text on the website, and that text's
translations. Safe to repeat. Edit hours later in Staff > Availability instead of running this again.
"""
import os
import sys
from datetime import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'spinalcure.settings')
os.environ.setdefault('DJANGO_ENV', 'development')
import django  # noqa: E402

django.setup()
from django.db import transaction  # noqa: E402

from appointments.models import DoctorAvailability  # noqa: E402
from clinic.content_i18n import source_hash  # noqa: E402
from clinic.models import ClinicProfile, Practitioner, Translation  # noqa: E402

SESSIONS = [(time(10, 30), time(13, 30)), (time(17, 30), time(20, 30))]
TEXT = {
    'en': 'Mon–Sat: 10:30 am – 1:30 pm, 5:30 pm – 8:30 pm\nSun: Closed',
    'ta': 'திங்கள்–சனி: காலை 10:30 – மதியம் 1:30, மாலை 5:30 – இரவு 8:30\nஞாயிறு: விடுமுறை',
    'hi': 'सोम–शनि: सुबह 10:30 – दोपहर 1:30, शाम 5:30 – रात 8:30\nरविवार: बंद',
    'te': 'సోమ–శని: ఉదయం 10:30 – మధ్యాహ్నం 1:30, సాయంత్రం 5:30 – రాత్రి 8:30\nఆదివారం: సెలవు',
    'ml': 'തിങ്കൾ–ശനി: രാവിലെ 10:30 – ഉച്ചയ്ക്ക് 1:30, വൈകിട്ട് 5:30 – രാത്രി 8:30\nഞായർ: അവധി',
    'kn': 'ಸೋಮ–ಶನಿ: ಬೆಳಿಗ್ಗೆ 10:30 – ಮಧ್ಯಾಹ್ನ 1:30, ಸಂಜೆ 5:30 – ರಾತ್ರಿ 8:30\nಭಾನುವಾರ: ರಜೆ',
}

with transaction.atomic():
    for doc in Practitioner.objects.filter(is_active=True):
        slot = (DoctorAvailability.objects.filter(practitioner=doc).values_list('slot_duration_minutes', flat=True).first() or 30)
        DoctorAvailability.objects.filter(practitioner=doc).delete()
        for day in range(6):
            for start, end in SESSIONS:
                DoctorAvailability.objects.create(practitioner=doc, day_of_week=day, start_time=start, end_time=end,
                                                  slot_duration_minutes=slot)
        print(f'{doc.name}: Mon-Sat {len(SESSIONS)} sessions a day, {slot}-minute appointments')

    clinic = ClinicProfile.objects.first()
    if clinic:
        clinic.working_hours = TEXT['en']
        clinic.save(update_fields=['working_hours'])
        for lang, text in TEXT.items():
            if lang == 'en':
                continue
            Translation.objects.update_or_create(
                model_label='clinic.clinicprofile', object_id=str(clinic.pk), field='working_hours', lang=lang,
                defaults={'value': text, 'status': 'final', 'method': 'manual', 'source_hash': source_hash(TEXT['en'])})
        print('Opening-hours text updated in English, Tamil, Hindi, Telugu, Malayalam and Kannada.')
