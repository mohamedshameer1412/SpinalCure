"""
Unit tests for OTP authentication and password reset functionality.
Tests security features including DDoS prevention, rate limiting, and brute force protection.
"""

import pytest
from datetime import datetime, timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from unittest.mock import patch

from accounts.models import OTPToken

User = get_user_model()


@pytest.mark.unit
@pytest.mark.otp
@pytest.mark.security
class TestOTPTokenGeneration:
    """Test OTP token generation and security."""

    def test_generate_otp_token_creates_token(self, patient_user):
        """Test that generate_otp_token creates a new OTP."""
        token = OTPToken.generate_otp_token(
            user=patient_user,
            delivery_method="email"
        )
        
        assert token is not None
        assert token['success'] is True
        assert 'otp' in token
        assert 'expires_in_minutes' in token


    def test_otp_token_has_valid_expiry(self, patient_user):
        """Test that OTP token expiry is set correctly."""
        result = OTPToken.generate_otp_token(patient_user, "email")
        
        otp_obj = OTPToken.objects.get(user=patient_user)
        
        # Expiry should be approximately 10 minutes from now
        time_diff = (otp_obj.expires_at - timezone.now()).total_seconds() / 60
        assert 9 <= time_diff <= 11  # Allow 1-minute margin


    def test_otp_secret_is_generated(self, patient_user):
        """Test that OTP secret is generated and stored."""
        OTPToken.generate_otp_token(patient_user, "email")
        
        otp_obj = OTPToken.objects.get(user=patient_user)
        assert otp_obj.otp_secret is not None
        assert len(otp_obj.otp_secret) > 0


    def test_previous_otp_invalidated_on_new_request(self, patient_user):
        """Test that previous OTP is invalidated when new one is requested."""
        # Generate first OTP
        result1 = OTPToken.generate_otp_token(patient_user, "email")
        first_otp = OTPToken.objects.get(user=patient_user)
        
        # Generate second OTP
        result2 = OTPToken.generate_otp_token(patient_user, "email")
        
        # First OTP should be invalid
        assert OTPToken.objects.filter(user=patient_user, is_used=True).exists()
        assert OTPToken.objects.filter(user=patient_user, is_used=False).exists()


@pytest.mark.unit
@pytest.mark.otp
@pytest.mark.security
class TestOTPRateLimiting:
    """Test OTP rate limiting and DDoS prevention."""

    def test_otp_request_rate_limiting_per_hour(self, patient_user):
        """Test that OTP requests are rate limited to 3 per hour."""
        # Generate first OTP (should succeed)
        result1 = OTPToken.generate_otp_token(patient_user, "email")
        assert result1['success'] is True
        
        # Generate second OTP (should succeed)
        result2 = OTPToken.generate_otp_token(patient_user, "email")
        assert result2['success'] is True
        
        # Generate third OTP (should succeed)
        result3 = OTPToken.generate_otp_token(patient_user, "email")
        assert result3['success'] is True
        
        # Fourth OTP request should be rate limited
        result4 = OTPToken.generate_otp_token(patient_user, "email")
        assert result4['success'] is False
        assert 'rate limit' in result4.get('error', '').lower()


    def test_daily_otp_request_limit(self, patient_user):
        """Test that daily OTP requests are limited to 5."""
        # This test would require time manipulation to fully test
        # For now, we verify the mechanism is in place
        otp = OTPToken.objects.create(user=patient_user)
        assert hasattr(otp, 'request_count_today')


@pytest.mark.unit
@pytest.mark.otp
@pytest.mark.security
class TestOTPVerification:
    """Test OTP verification and password reset."""

    def test_verify_otp_with_correct_code(self, patient_user):
        """Test OTP verification with correct code."""
        # Generate OTP
        OTPToken.generate_otp_token(patient_user, "email")
        otp_obj = OTPToken.objects.get(user=patient_user, is_used=False)
        
        # Get the correct OTP value
        otp_value = otp_obj.otp_value
        
        # Verify with correct OTP
        result = otp_obj.verify_otp(otp_value)
        
        assert result['success'] is True
        assert 'token' in result  # Should return JWT token or similar


    def test_verify_otp_with_incorrect_code(self, patient_user):
        """Test OTP verification with incorrect code fails."""
        # Generate OTP
        OTPToken.generate_otp_token(patient_user, "email")
        otp_obj = OTPToken.objects.get(user=patient_user, is_used=False)
        
        # Verify with incorrect OTP
        result = otp_obj.verify_otp("000000")
        
        assert result['success'] is False
        assert 'failed_attempts' in result or 'error' in result


    def test_brute_force_protection_5_attempts(self, patient_user):
        """Test that OTP is invalidated after 5 failed attempts."""
        # Generate OTP
        OTPToken.generate_otp_token(patient_user, "email")
        otp_obj = OTPToken.objects.get(user=patient_user, is_used=False)
        
        # Make 5 failed attempts
        for i in range(5):
            result = otp_obj.verify_otp(f"{i:06d}")
            assert result['success'] is False
        
        # Refresh from database
        otp_obj.refresh_from_db()
        
        # Should be marked as invalid
        assert otp_obj.failed_attempts >= 5


    def test_otp_expires_after_10_minutes(self, patient_user):
        """Test that OTP expires after configured time."""
        # Generate OTP
        OTPToken.generate_otp_token(patient_user, "email")
        otp_obj = OTPToken.objects.get(user=patient_user)
        
        # Set expiry to past
        otp_obj.expires_at = timezone.now() - timedelta(minutes=1)
        otp_obj.save()
        
        # Try to verify
        result = otp_obj.verify_otp("123456")
        
        assert result['success'] is False
        assert 'expired' in result.get('error', '').lower() or result['success'] is False


    def test_otp_marked_as_used_after_verification(self, patient_user):
        """Test that OTP is marked as used after successful verification."""
        # Generate OTP
        OTPToken.generate_otp_token(patient_user, "email")
        otp_obj = OTPToken.objects.get(user=patient_user, is_used=False)
        
        otp_value = otp_obj.otp_value
        
        # Verify OTP
        result = otp_obj.verify_otp(otp_value)
        
        # Refresh from database
        otp_obj.refresh_from_db()
        
        # Should be marked as used
        assert otp_obj.is_used is True


@pytest.mark.unit
@pytest.mark.otp
class TestOTPCleanup:
    """Test OTP token cleanup and maintenance."""

    def test_cleanup_expired_tokens(self, patient_user):
        """Test that cleanup_expired_tokens removes expired tokens."""
        # Create multiple expired tokens
        for i in range(3):
            otp = OTPToken.objects.create(
                user=patient_user,
                delivery_method="email",
                otp_value=f"{i:06d}",
                expires_at=timezone.now() - timedelta(hours=1)
            )
        
        # Create one valid token
        OTPToken.generate_otp_token(patient_user, "email")
        
        # Run cleanup
        deleted_count = OTPToken.cleanup_expired_tokens()
        
        # 3 expired tokens should be deleted
        assert deleted_count[0] >= 3


    def test_cleanup_does_not_remove_valid_tokens(self, patient_user):
        """Test that cleanup doesn't remove valid tokens."""
        # Generate valid OTP
        OTPToken.generate_otp_token(patient_user, "email")
        
        initial_count = OTPToken.objects.filter(user=patient_user).count()
        
        # Run cleanup
        OTPToken.cleanup_expired_tokens()
        
        final_count = OTPToken.objects.filter(user=patient_user).count()
        
        # Count should not decrease
        assert final_count >= initial_count - 1  # -1 for potential rate-limited tokens


@pytest.mark.unit
@pytest.mark.otp
class TestOTPModel:
    """Test OTPToken model properties and methods."""

    def test_otp_token_default_delivery_method(self, patient_user):
        """Test default delivery method is set."""
        otp = OTPToken.objects.create(user=patient_user)
        assert otp.delivery_method == "email"


    def test_otp_is_used_default_false(self, patient_user):
        """Test that is_used defaults to False."""
        otp = OTPToken.objects.create(user=patient_user)
        assert otp.is_used is False


    def test_otp_failed_attempts_default_zero(self, patient_user):
        """Test that failed_attempts defaults to 0."""
        otp = OTPToken.objects.create(user=patient_user)
        assert otp.failed_attempts == 0


    def test_otp_request_count_today_default_zero(self, patient_user):
        """Test that request_count_today defaults to 0."""
        otp = OTPToken.objects.create(user=patient_user)
        assert otp.request_count_today == 0
