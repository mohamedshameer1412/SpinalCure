"""Store a sharp thumbnail for every YouTube story that has none (or all of them with --force).

    python manage.py import_story_thumbnails [--force]

Uploaded thumbnails are never replaced, even with --force.
"""
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db.models import Q

from clinic import stories
from clinic.models import TestimonialVideo


class Command(BaseCommand):
    help = 'Import the best YouTube frame as the stored thumbnail of each story video.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Replace imported frames too (never uploads).')

    def handle(self, *args, force=False, **opts):
        qs = TestimonialVideo.objects.filter(platform='youtube').exclude(thumbnail_source='upload')
        if not force:
            qs = qs.filter(Q(thumbnail='') | Q(thumbnail__isnull=True))
        done = failed = 0
        for v in qs:
            try:
                stories.import_frame(v, 'platform')
                v.save()
                stories.warm_renditions(v)
                done += 1
            except ValueError as e:
                failed += 1
                self.stderr.write(f'{v.video_id}: {e}')
        # stored thumbnails from earlier runs / uploads: make sure their crops exist before a visitor asks for them
        keep = set()
        for v in TestimonialVideo.objects.exclude(Q(thumbnail='') | Q(thumbnail__isnull=True)):
            keep |= stories.warm_renditions(v)
        _, files = default_storage.listdir('stories/r')
        stale = [f for f in files if f not in keep]
        for f in stale:                                   # crops of replaced thumbnails or old focal points
            default_storage.delete(f'stories/r/{f}')
        if stale:
            self.stdout.write(f'{len(stale)} old crops removed')
        self.stdout.write(self.style.SUCCESS(f'{done} thumbnails imported, {failed} failed'))
