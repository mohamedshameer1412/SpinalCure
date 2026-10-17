"""
Re-encrypt every encrypted column with the first key in FERNET_KEYS.

Rotation: put the new key first, keep the old key after it
(FERNET_KEYS=new,old), run this command, then remove the old key.
"""
from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction

from spinalcure.fields import _EncryptedMixin, EncryptedJSONField


class Command(BaseCommand):
    help = 'Re-encrypt all encrypted fields with the current primary key.'

    def handle(self, *args, **options):
        for model in apps.get_models():
            fields = [f.name for f in model._meta.concrete_fields if isinstance(f, (_EncryptedMixin, EncryptedJSONField))]
            if not fields:
                continue
            if any(f.name == 'phone_hash' for f in model._meta.concrete_fields):
                fields.append('phone_hash')  # recomputed in Patient.save()
            count = 0
            # Rows are decrypted on load (any key) and encrypted on save (primary key).
            for obj in model._base_manager.only('pk', *fields).iterator(chunk_size=500):
                with transaction.atomic():
                    obj.save(update_fields=fields)
                count += 1
            self.stdout.write(f'{model._meta.label}: re-encrypted {count} rows ({", ".join(fields)})')
        self.stdout.write(self.style.SUCCESS('Done. You can now remove old keys from FERNET_KEYS.'))
