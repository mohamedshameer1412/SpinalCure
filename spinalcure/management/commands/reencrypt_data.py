"""Re-encrypt every Encrypted*Field value with the primary (first) key in FERNET_KEYS."""
from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction

from spinalcure import fields as enc


ENCRYPTED = (enc.EncryptedCharField, enc.EncryptedTextField, enc.EncryptedEmailField, enc.EncryptedJSONField)


class Command(BaseCommand):
    help = 'Re-encrypt all encrypted model fields with the first key in FERNET_KEYS (use after key rotation).'

    def handle(self, *args, **options):
        total = 0
        for model in apps.get_models():
            names = [f.name for f in model._meta.get_fields() if isinstance(f, ENCRYPTED)]
            if not names:
                continue
            with transaction.atomic():
                for obj in model.objects.all().iterator():
                    # Values were decrypted on load; saving re-encrypts them with the primary key.
                    model.objects.filter(pk=obj.pk).update(**{n: getattr(obj, n) for n in names})
                    total += 1
            self.stdout.write(f'{model._meta.label}: fields {names}')
        self.stdout.write(self.style.SUCCESS(f'Re-encrypted {total} rows.'))
