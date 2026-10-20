from django.core.management.base import BaseCommand

from payments import online, razorpay as rzp


class Command(BaseCommand):
    help = 'Ask Razorpay about open online orders and record captured payments whose webhook never arrived.'

    def add_arguments(self, parser):
        parser.add_argument('--older-than', type=int, default=10, help='Only orders created at least this many minutes ago.')

    def handle(self, *args, **opts):
        if not rzp.enabled():
            self.stdout.write('Razorpay is not configured; nothing to do.')
            return
        checked, applied = online.reconcile(opts['older_than'])
        self.stdout.write(f'Checked {checked} open order(s); recorded {applied} payment(s).')
