"""Export the public website content (no patients, payments, staff accounts or logs) for a fresh server.

    DJANGO_ENV=development python scripts/export_content.py

Writes deploy/content.json and copies every file those records use into deploy/media/.
deploy/setup_server.py loads both on the server.
"""
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'spinalcure.settings')
os.environ.setdefault('DJANGO_ENV', 'development')
import django  # noqa: E402

django.setup()
from django.conf import settings  # noqa: E402
from django.core import serializers  # noqa: E402
from django.db.models import FileField  # noqa: E402

from appointments.models import BookingSettings, DoctorAvailability, TimeOff  # noqa: E402
from clinic.blog_models import BlogPost, BlogTag  # noqa: E402
from clinic.models import (FAQ, ClinicAboutImage, ClinicProfile, ClinicService, ClinicTestimonial,  # noqa: E402
                           FeaturedPatient, GalleryItem, HeroCarouselImage, Practitioner, ProblemCategory,
                           TestimonialVideo, Translation)
from courses.models import Course, CourseBatch  # noqa: E402
from events.models import Event  # noqa: E402
from patients.models import SessionPackage  # noqa: E402

OUT = ROOT / 'deploy'
MEDIA_OUT = OUT / 'media'

# parents before children, so the fixture loads in order
querysets = [
    ClinicProfile.objects.all(), Practitioner.objects.all(), ClinicAboutImage.objects.all(), ClinicService.objects.all(),
    HeroCarouselImage.objects.all(), ProblemCategory.objects.all(), FAQ.objects.all(),
    ClinicTestimonial.objects.filter(is_published=True, submitted_via='staff'),
    TestimonialVideo.objects.all(), GalleryItem.objects.all(), FeaturedPatient.objects.all(),
    BlogTag.objects.all(), BlogPost.objects.all(),
    Course.objects.all(), CourseBatch.objects.all(), Event.objects.all(),
    DoctorAvailability.objects.all(), TimeOff.objects.all(), BookingSettings.objects.all(), SessionPackage.objects.all(),
]
objects = []
for qs in querysets:
    for obj in qs:
        if isinstance(obj, Event):
            obj.organizer = None                     # staff accounts are not exported
        if isinstance(obj, TimeOff):
            obj.created_by = None
        objects.append(obj)
exported_labels = {qs.model._meta.label_lower for qs in querysets}
objects += list(Translation.objects.filter(model_label__in=exported_labels))

OUT.mkdir(exist_ok=True)
with open(OUT / 'content.json', 'w', encoding='utf-8') as fh:
    serializers.serialize('json', objects, stream=fh, indent=1, ensure_ascii=False)

# files referenced by the exported records (+ the clinic logo's dark/white variants)
media_root = Path(settings.MEDIA_ROOT)
names = set()
for obj in objects:
    for f in obj._meta.get_fields():
        if isinstance(f, FileField) and getattr(obj, f.name):
            names.add(getattr(obj, f.name).name)
clinic = ClinicProfile.objects.first()
if clinic and clinic.logo:
    stem, ext = os.path.splitext(clinic.logo.name)
    names |= {f'{stem}_on_dark{ext}', f'{stem}_white{ext}'}
names |= {str(p.relative_to(media_root)).replace('\\', '/') for p in (media_root / 'stories' / 'r').glob('*')} \
    if (media_root / 'stories' / 'r').exists() else set()

if MEDIA_OUT.exists():
    shutil.rmtree(MEDIA_OUT)
copied = missing = 0
for name in sorted(names):
    src = media_root / name
    if not src.is_file():
        missing += 1
        continue
    dst = MEDIA_OUT / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    copied += 1
print(f'{len(objects)} records -> deploy/content.json; {copied} media files -> deploy/media ({missing} missing)')
