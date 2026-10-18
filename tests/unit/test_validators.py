"""
Unit tests for input validators.
Tests all custom validators used across the application for data integrity.
"""

import pytest
from django.core.exceptions import ValidationError
from spinalcure.validators import (
    validate_phone_number,
    validate_not_in_past,
    validate_not_in_future,
    validate_time_range,
    validate_positive_amount,
    validate_percentage,
    validate_gstin,
    validate_ifsc_code,
    validate_upi,
    validate_email_format
)
from datetime import datetime, timedelta, time


@pytest.mark.unit
class TestPhoneNumberValidator:
    """Test phone number validation."""

    def test_valid_phone_numbers(self):
        """Test that valid phone numbers pass."""
        valid_numbers = [
            "9876543210",
            "9123456789",
            "8888888888",
            "+919876543210",
            "+1 (555) 123-4567"
        ]
        
        for phone in valid_numbers:
            try:
                validate_phone_number(phone)
            except ValidationError:
                pytest.fail(f"Valid phone '{phone}' rejected")


    def test_invalid_phone_numbers(self):
        """Test that invalid phone numbers fail."""
        invalid_numbers = [
            "123",  # Too short
            "123456789123456789",  # Too long
            "abcdefghij",  # Non-numeric
            "",  # Empty
        ]
        
        for phone in invalid_numbers:
            with pytest.raises(ValidationError):
                validate_phone_number(phone)


@pytest.mark.unit
class TestDateValidators:
    """Test date validation functions."""

    def test_validate_not_in_past_future_dates(self):
        """Test that future dates pass validate_not_in_past."""
        future_date = datetime.now() + timedelta(days=1)
        
        try:
            validate_not_in_past(future_date)
        except ValidationError:
            pytest.fail("Future date rejected by validate_not_in_past")


    def test_validate_not_in_past_rejects_past_dates(self):
        """Test that past dates fail validate_not_in_past."""
        past_date = datetime.now() - timedelta(days=1)
        
        with pytest.raises(ValidationError):
            validate_not_in_past(past_date)


    def test_validate_not_in_future_past_dates(self):
        """Test that past dates pass validate_not_in_future."""
        past_date = datetime.now() - timedelta(days=1)
        
        try:
            validate_not_in_future(past_date)
        except ValidationError:
            pytest.fail("Past date rejected by validate_not_in_future")


    def test_validate_not_in_future_rejects_future_dates(self):
        """Test that future dates fail validate_not_in_future."""
        future_date = datetime.now() + timedelta(days=1)
        
        with pytest.raises(ValidationError):
            validate_not_in_future(future_date)


@pytest.mark.unit
class TestTimeRangeValidator:
    """Test time range validation."""

    def test_valid_time_range(self):
        """Test that valid time ranges pass."""
        start_time = time(9, 0)
        end_time = time(17, 0)
        
        try:
            validate_time_range(start_time, end_time)
        except ValidationError:
            pytest.fail("Valid time range rejected")


    def test_invalid_time_range_equal_times(self):
        """Test that equal start and end times fail."""
        same_time = time(9, 0)
        
        with pytest.raises(ValidationError):
            validate_time_range(same_time, same_time)


    def test_invalid_time_range_reversed(self):
        """Test that reversed time range fails."""
        start_time = time(17, 0)
        end_time = time(9, 0)
        
        with pytest.raises(ValidationError):
            validate_time_range(start_time, end_time)


@pytest.mark.unit
class TestAmountValidators:
    """Test financial amount validation."""

    def test_validate_positive_amount_positive_values(self):
        """Test that positive amounts pass."""
        amounts = [0.01, 1, 100, 1000.50, 99999.99]
        
        for amount in amounts:
            try:
                validate_positive_amount(amount)
            except ValidationError:
                pytest.fail(f"Valid amount {amount} rejected")


    def test_validate_positive_amount_rejects_zero(self):
        """Test that zero is rejected."""
        with pytest.raises(ValidationError):
            validate_positive_amount(0)


    def test_validate_positive_amount_rejects_negative(self):
        """Test that negative amounts are rejected."""
        with pytest.raises(ValidationError):
            validate_positive_amount(-100)


    def test_validate_percentage_valid_ranges(self):
        """Test that percentages 0-100 pass."""
        valid_percentages = [0, 1, 50, 99, 100]
        
        for percent in valid_percentages:
            try:
                validate_percentage(percent)
            except ValidationError:
                pytest.fail(f"Valid percentage {percent} rejected")


    def test_validate_percentage_rejects_negative(self):
        """Test that negative percentages fail."""
        with pytest.raises(ValidationError):
            validate_percentage(-1)


    def test_validate_percentage_rejects_over_100(self):
        """Test that percentages > 100 fail."""
        with pytest.raises(ValidationError):
            validate_percentage(101)


@pytest.mark.unit
class TestGSTINValidator:
    """Test GSTIN (Indian GST) validation."""

    def test_valid_gstin(self):
        """Test that valid GSTINs pass."""
        valid_gstins = [
            "27AAABZ1234K1Z1",
            "29AAFFF1234K1Z1",
            "06AAACN5001J1Z3"
        ]
        
        for gstin in valid_gstins:
            try:
                validate_gstin(gstin)
            except ValidationError:
                pytest.fail(f"Valid GSTIN '{gstin}' rejected")


    def test_invalid_gstin_format(self):
        """Test that invalid GSTIN formats fail."""
        invalid_gstins = [
            "123456789012345",  # Wrong length
            "INVALID_GSTIN",
            "27AAABZ1234K1Z",  # Missing digit
        ]
        
        for gstin in invalid_gstins:
            with pytest.raises(ValidationError):
                validate_gstin(gstin)


@pytest.mark.unit
class TestIFSCValidator:
    """Test IFSC (Indian bank code) validation."""

    def test_valid_ifsc(self):
        """Test that valid IFSC codes pass."""
        valid_ifscs = [
            "SBIN0001234",
            "HDFC0000001",
            "ICIC0000001"
        ]
        
        for ifsc in valid_ifscs:
            try:
                validate_ifsc_code(ifsc)
            except ValidationError:
                pytest.fail(f"Valid IFSC '{ifsc}' rejected")


    def test_invalid_ifsc_format(self):
        """Test that invalid IFSC formats fail."""
        invalid_ifscs = [
            "INVALID",  # Too short
            "SBIN000123456",  # Too long
            "123456789012",  # All numbers
        ]
        
        for ifsc in invalid_ifscs:
            with pytest.raises(ValidationError):
                validate_ifsc_code(ifsc)


@pytest.mark.unit
class TestUPIValidator:
    """Test UPI (Unified Payments Interface) validation."""

    def test_valid_upi_ids(self):
        """Test that valid UPI IDs pass."""
        valid_upis = [
            "user@upi",
            "clinic@okhdfcbank",
            "payment@upi"
        ]
        
        for upi in valid_upis:
            try:
                validate_upi(upi)
            except ValidationError:
                pytest.fail(f"Valid UPI '{upi}' rejected")


    def test_invalid_upi_format(self):
        """Test that invalid UPI formats fail."""
        invalid_upis = [
            "invalid",  # No @
            "user@",  # Missing provider
            "@upi",  # Missing username
        ]
        
        for upi in invalid_upis:
            with pytest.raises(ValidationError):
                validate_upi(upi)


@pytest.mark.unit
class TestEmailValidator:
    """Test email format validation."""

    def test_valid_email_formats(self):
        """Test that valid emails pass."""
        valid_emails = [
            "user@example.com",
            "patient@spinalcure.com",
            "doctor.name@hospital.org",
            "test+tag@domain.co.uk"
        ]
        
        for email in valid_emails:
            try:
                validate_email_format(email)
            except ValidationError:
                pytest.fail(f"Valid email '{email}' rejected")


    def test_invalid_email_formats(self):
        """Test that invalid emails fail."""
        invalid_emails = [
            "plainaddress",  # No @
            "@example.com",  # No username
            "user@",  # No domain
            "user name@example.com",  # Space
        ]
        
        for email in invalid_emails:
            with pytest.raises(ValidationError):
                validate_email_format(email)
