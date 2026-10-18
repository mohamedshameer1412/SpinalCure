"""
Keyed blind index for exact-match lookups on randomly-encrypted fields.

Fernet ciphertext differs on every encryption, so `filter(phone=...)` can never match.
A truncated HMAC of the normalised value is stored beside the ciphertext and queried instead.
It reveals only equality, and cannot be recomputed without SECRET_KEY.
"""
import hashlib
import hmac
import re

from django.conf import settings


def normalise_phone(value):
    """Digits only; compare on the last 10 digits so '+91 98765-43210' == '9876543210'."""
    digits = re.sub(r'\D', '', value or '')
    return digits[-10:] if len(digits) >= 10 else digits


def blind_index(value):
    if not value:
        return ''
    key = hashlib.sha256(b'spinalcure-blind-index:' + settings.SECRET_KEY.encode()).digest()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def phone_index(value):
    return blind_index(normalise_phone(value))
