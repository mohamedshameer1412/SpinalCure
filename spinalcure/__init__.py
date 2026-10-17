from django.db.models import UUIDField
import uuid

def custom_get_db_prep_value(self, value, connection, prepared=False):
    """
    Monkeypatch for Django 6.0 + MySQL `has_native_uuid_field` bug.
    Ensures UUIDs are consistently formatted as 32-character hex strings
    without hyphens to match `char(32)` storage and avoid `NotUpdated` errors.
    """
    if value is None:
        return None
    if not isinstance(value, uuid.UUID):
        try:
            value = uuid.UUID(value)
        except ValueError:
            pass
    if isinstance(value, uuid.UUID):
        return value.hex
    return value

UUIDField.get_db_prep_value = custom_get_db_prep_value
