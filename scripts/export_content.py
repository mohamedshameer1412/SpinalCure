"""Export the clinic's real setup for a fresh server: NO patients, payments, expenses, courses, students, events or
appointments.

    DJANGO_ENV=development python scripts/export_content.py

Exports: clinic profile and website content, practitioners, staff accounts with their existing password hashes (the
same sign-in details keep working), staff profiles, ID cards and card branding, doctor availability and booking rules.
Writes deploy/content.json, copies public images to deploy/media/ and staff photos to deploy/private_media/.
deploy/setup_server.py loads all of it on the server. deploy/content.json holds password hashes: keep it private.
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
from spinalcure.private_media import PrivateStorage  # noqa: E402

from appointments.models import BookingSettings, DoctorAvailability  # noqa: E402
from clinic.blog_models import BlogPost, BlogTag  # noqa: E402
from clinic.models import (FAQ, ClinicAboutImage, ClinicProfile, ClinicService, ClinicTestimonial,  # noqa: E402
                           FeaturedPatient, GalleryItem, HeroCarouselImage, Practitioner, ProblemCategory,
                           TestimonialVideo, Translation)
from accounts.models import CustomUser, StaffProfile  # noqa: E402
from idcards.models import IDCard, IDCardBranding  # noqa: E402

OUT = ROOT / 'deploy'
MEDIA_OUT = OUT / 'media'
PRIVATE_OUT = OUT / 'private_media'

# parents before children, so the fixture loads in order
querysets = [
    ClinicProfile.objects.all(), Practitioner.objects.all(), ClinicAboutImage.objects.all(), ClinicService.objects.all(),
    CustomUser.objects.order_by('date_joined'), StaffProfile.objects.all(), IDCardBranding.objects.all(),
    IDCard.objects.order_by('issued_on', 'id'),
    HeroCarouselImage.objects.all(), ProblemCategory.objects.all(), FAQ.objects.all(),
    ClinicTestimonial.objects.filter(is_published=True, submitted_via='staff'),
    TestimonialVideo.objects.all(), GalleryItem.objects.all(), FeaturedPatient.objects.all(),
    BlogTag.objects.all(), BlogPost.objects.all(),
    DoctorAvailability.objects.all(), BookingSettings.objects.all(),
]
objects = []
for qs in querysets:
    for obj in qs:
        objects.append(obj)
exported_labels = {qs.model._meta.label_lower for qs in querysets}
objects += list(Translation.objects.filter(model_label__in=exported_labels))

OUT.mkdir(exist_ok=True)
with open(OUT / 'content.json', 'w', encoding='utf-8') as fh:
    serializers.serialize('json', objects, stream=fh, indent=1, ensure_ascii=False)

# files referenced by the exported records (+ the clinic logo's dark/white variants)
media_root = Path(settings.MEDIA_ROOT)
private_root = Path(settings.PRIVATE_MEDIA_ROOT)
names, private_names = set(), set()
for obj in objects:
    for f in obj._meta.get_fields():
        if isinstance(f, FileField) and getattr(obj, f.name):
            (private_names if isinstance(f.storage, PrivateStorage) else names).add(getattr(obj, f.name).name)
clinic = ClinicProfile.objects.first()
if clinic and clinic.logo:
    stem, ext = os.path.splitext(clinic.logo.name)
    names |= {f'{stem}_on_dark{ext}', f'{stem}_white{ext}'}
names |= {str(p.relative_to(media_root)).replace('\\', '/') for p in (media_root / 'stories' / 'r').glob('*')} \
    if (media_root / 'stories' / 'r').exists() else set()

for target in (MEDIA_OUT, PRIVATE_OUT):
    if target.exists():
        shutil.rmtree(target)


def copy_files(file_names, root, out):
    copied = missing = 0
    for name in sorted(file_names):
        src = root / name
        if not src.is_file():
            missing += 1
            continue
        dst = out / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    return copied, missing


copied, missing = copy_files(names, media_root, MEDIA_OUT)
p_copied, p_missing = copy_files(private_names, private_root, PRIVATE_OUT)
by_model = {}
for o in objects:
    by_model[o._meta.label] = by_model.get(o._meta.label, 0) + 1
print(f'{len(objects)} records -> deploy/content.json; {copied} public images -> deploy/media ({missing} missing); '
      f'{p_copied} staff photos -> deploy/private_media ({p_missing} missing)')
print('  ' + ', '.join(f'{k}: {v}' for k, v in sorted(by_model.items())))
