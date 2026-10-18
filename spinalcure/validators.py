"""
Custom validators for SpinalCure models.
"""
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from datetime import datetime
from django.utils import timezone
import re


def validate_phone_number(value):
    """Validate phone number format."""
    if not re.match(r'^[+]?[0-9]{7,15}$', re.sub(r'[\s().-]', '', value or '')):
        raise ValidationError(
            _('Phone number must contain 7-15 digits.'),
            code='invalid_phone'
        )


def _as_local_date(value):
    """Accept date or datetime; compare in the project's timezone."""
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.date()
    return value


def validate_not_in_past(value):
    """Validate that date is not in the past."""
    if _as_local_date(value) < timezone.localdate():
        raise ValidationError(
            _('Date cannot be in the past.'),
            code='date_in_past'
        )


def validate_not_in_future(value):
    """Validate that date is not in the future."""
    if _as_local_date(value) > timezone.localdate():
        raise ValidationError(
            _('Date cannot be in the future.'),
            code='date_in_future'
        )


def validate_time_range(start_time, end_time):
    """Validate that start_time < end_time."""
    if start_time >= end_time:
        raise ValidationError(
            _('Start time must be before end time.'),
            code='invalid_time_range'
        )


def validate_positive_amount(value):
    """Validate that amount is positive."""
    if value <= 0:
        raise ValidationError(
            _('Amount must be greater than 0.'),
            code='invalid_amount'
        )


def validate_percentage(value):
    """Validate that value is between 0 and 100."""
    if not (0 <= value <= 100):
        raise ValidationError(
            _('Value must be between 0 and 100.'),
            code='invalid_percentage'
        )


def validate_gstin(value):
    """Validate GST Identification Number format (India)."""
    if value and not re.match(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$', value):
        raise ValidationError(
            _('Invalid GST Identification Number format.'),
            code='invalid_gstin'
        )


def validate_ifsc_code(value):
    """Validate IFSC code format (India)."""
    if value and not re.match(r'^[A-Z]{4}0[A-Z0-9]{6}$', value):
        raise ValidationError(
            _('Invalid IFSC Code format.'),
            code='invalid_ifsc'
        )


def validate_upi(value):
    """Validate UPI ID format."""
    if value and not re.match(r'^[a-zA-Z0-9._-]+@[a-zA-Z]{3,}$', value):
        raise ValidationError(
            _('Invalid UPI ID format.'),
            code='invalid_upi'
        )


def validate_email_format(value):
    """Validate an email address using Django's validator with a clearer message."""
    from django.core.validators import validate_email
    try:
        validate_email(value)
    except ValidationError:
        raise ValidationError(_('Enter a valid email address.'))
