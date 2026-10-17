"""
Field-level encryption (Fernet: AES-128-CBC + HMAC-SHA256) for patient PII/PHI.

Keys come from settings.FERNET_KEYS (env FERNET_KEYS, comma separated).
The first key encrypts; all keys decrypt, so keys can be rotated with
`manage.py rotate_encryption_key`.
"""
import json
from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from django.conf import settings
from django.db import models

# Every Fernet token starts with version byte 0x80, i.e. "gAAAAA" in urlsafe base64.
_TOKEN_PREFIX = 'gAAAAA'


@lru_cache(maxsize=1)
def _fernet_for(keys):
    return MultiFernet([Fernet(k.encode('utf-8')) for k in keys])


def get_fernet():
    return _fernet_for(tuple(settings.FERNET_KEYS))


def encrypt_str(value):
    return get_fernet().encrypt(value.encode('utf-8')).decode('utf-8')


def decrypt_str(value):
    """Decrypt a token; return legacy plaintext unchanged. A token we cannot decrypt is a key
    misconfiguration and must fail loudly, otherwise the next save would double-encrypt it."""
    if not value.startswith(_TOKEN_PREFIX):
        return value
    try:
        return get_fernet().decrypt(value.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        raise RuntimeError('Encrypted field could not be decrypted: FERNET_KEYS does not contain the key used to write it.')


class _EncryptedMixin:
    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == '':
            return value
        return encrypt_str(str(value))

    def from_db_value(self, value, expression, connection):
        if value is None or value == '':
            return value
        return decrypt_str(value)


class EncryptedCharField(_EncryptedMixin, models.CharField):
    def get_internal_type(self):
        return "CharField"


class EncryptedEmailField(_EncryptedMixin, models.EmailField):
    def get_internal_type(self):
        return "CharField"


class EncryptedTextField(_EncryptedMixin, models.TextField):
    def get_internal_type(self):
        return "TextField"


class EncryptedJSONField(models.JSONField):
    def get_internal_type(self):
        return "TextField"  # ciphertext is not valid JSON, so store as text

    def get_db_prep_value(self, value, connection, prepared=False):
        if value is None:
            return None
        return encrypt_str(json.dumps(value, cls=self.encoder))

    def from_db_value(self, value, expression, connection):
        if value is None or value == '':
            return value
        plain = decrypt_str(value)
        try:
            return json.loads(plain)
        except (TypeError, ValueError):
            return plain


def phone_digest(phone):
    """Keyed hash of a phone number (last 10 digits) so encrypted phones can be looked up exactly.
    Keyed with SECRET_KEY: after changing SECRET_KEY run `manage.py rotate_encryption_key` to rebuild."""
    from django.utils.crypto import salted_hmac
    digits = ''.join(ch for ch in str(phone or '') if ch.isdigit())[-10:]
    if len(digits) < 6:
        return ''
    return salted_hmac('patients.phone_digest', digits).hexdigest()
