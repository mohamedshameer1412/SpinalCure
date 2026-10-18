"""
Search over encrypted patient fields.

Fernet ciphertext is randomised, so SQL LIKE/icontains on `name`, `phone`, `email` etc. matches
nothing meaningful. Matching therefore happens after decryption. That is O(patients) per search,
acceptable for a single clinic; revisit with a search index if the patient count grows past
tens of thousands.
"""
import re

from django.db.models import Q

from .models import Patient

SEARCH_FIELDS = ('name', 'phone', 'whatsapp_no', 'email', 'chief_complaint', 'medical_history')
_NON_DIGIT = re.compile(r'\D')


def matching_patient_ids(query, fields=SEARCH_FIELDS):
    needle = (query or '').strip().lower()
    if not needle:
        return []
    needle_digits = _NON_DIGIT.sub('', needle)
    ids = []
    for row in Patient.objects.only('id', *fields).iterator(chunk_size=500):
        for field in fields:
            value = (getattr(row, field) or '')
            if not isinstance(value, str):
                continue
            haystack = value.lower()
            if needle in haystack or (needle_digits and field in ('phone', 'whatsapp_no')
                                      and needle_digits in _NON_DIGIT.sub('', haystack)):
                ids.append(row.pk)
                break
    return ids


def patient_q(query, prefix='', fields=SEARCH_FIELDS):
    """Q object selecting rows whose related patient matches `query` (`prefix` e.g. 'patient__')."""
    return Q(**{f'{prefix}pk__in': matching_patient_ids(query, fields)})
