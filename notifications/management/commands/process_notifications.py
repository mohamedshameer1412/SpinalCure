"""Retry failed/pending notification deliveries that are due. Run every few minutes from cron:

    */5 * * * *  python manage.py process_notifications
"""
from django.core.management.base import BaseCommand

from notifications.service import retry_due


class Command(BaseCommand):
    help = 'Retry due notification deliveries (email/SMS/WhatsApp) with backoff.'

    def handle(self, *args, **options):
        self.stdout.write(f'Processed {retry_due()} deliveries.')
