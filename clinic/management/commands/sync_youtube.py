"""Fetch the clinic's newest YouTube videos and Shorts (title + caption) into Reels & Shorts.

    python manage.py sync_youtube          # run it from cron, e.g. every hour
"""
from django.core.management.base import BaseCommand, CommandError

from clinic import youtube_sync


class Command(BaseCommand):
    help = 'Import new uploads from the clinic YouTube channel.'

    def handle(self, *args, **opts):
        try:
            added, existing = youtube_sync.sync()
        except youtube_sync.SyncError as e:
            raise CommandError(str(e))
        self.stdout.write(f'{added} new, {existing} already in the library.')
