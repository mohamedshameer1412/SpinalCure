import json
from django.db import models
from cryptography.fernet import Fernet
from django.conf import settings

def get_fernet():
    return Fernet(settings.FERNET_KEY.encode('utf-8'))

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
        # We want to encrypt the JSON string
        value_str = super().get_prep_value(value)
        if value_str is None or value_str == '':
            return value_str
        f = get_fernet()
        return f.encrypt(value_str.encode('utf-8')).decode('utf-8')

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
