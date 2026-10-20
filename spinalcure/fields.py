import json
from django.db import models
from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings


def get_fernet():
    """Encrypt with the first configured key; decrypt with any (supports key rotation)."""
    return MultiFernet([Fernet(k.encode('utf-8')) for k in settings.FERNET_KEYS])

class EncryptedCharField(models.CharField):
    def get_internal_type(self):
        return "CharField"

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == '':
            return value
        f = get_fernet()
        return f.encrypt(value.encode('utf-8')).decode('utf-8')

    def from_db_value(self, value, expression, connection):
        if value is None or value == '':
            return value
        f = get_fernet()
        try:
            return f.decrypt(value.encode('utf-8')).decode('utf-8')
        except Exception:
            return value


class EncryptedEmailField(models.EmailField):
    def get_internal_type(self):
        return "CharField"

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == '':
            return value
        f = get_fernet()
        return f.encrypt(value.encode('utf-8')).decode('utf-8')

    def from_db_value(self, value, expression, connection):
        if value is None or value == '':
            return value
        f = get_fernet()
        try:
            return f.decrypt(value.encode('utf-8')).decode('utf-8')
        except Exception:
            return value


class EncryptedTextField(models.TextField):
    def get_internal_type(self):
        return "TextField"

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == '':
            return value
        f = get_fernet()
        return f.encrypt(value.encode('utf-8')).decode('utf-8')

    def from_db_value(self, value, expression, connection):
        if value is None or value == '':
            return value
        f = get_fernet()
        try:
            return f.decrypt(value.encode('utf-8')).decode('utf-8')
        except Exception:
            return value


class EncryptedJSONField(models.JSONField):
    def get_internal_type(self):
        return "TextField"  # Store as text because DB JSON validation will fail on ciphertext

    def get_prep_value(self, value):
        # Serialise ourselves: since Django 4.2 JSONField.get_prep_value returns the Python object, not a string
        if value is None:
            return None
        value_str = json.dumps(value, cls=self.encoder)
        return get_fernet().encrypt(value_str.encode('utf-8')).decode('utf-8')

    def get_db_prep_value(self, value, connection, prepared=False):
        # store the ciphertext as plain text; JSONField would JSON-encode it a second time
        return value if prepared else self.get_prep_value(value)

    def from_db_value(self, value, expression, connection):
        if value is None or value == '':
            return value
        f = get_fernet()
        try:
            decrypted = f.decrypt(value.encode('utf-8')).decode('utf-8')
            return json.loads(decrypted)
        except Exception:
            # If decryption fails, it might be plain JSON string from before encryption
            try:
                if isinstance(value, str):
                    return json.loads(value)
            except Exception:
                pass
            return value
