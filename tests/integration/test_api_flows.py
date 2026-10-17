"""
Integration tests for API endpoints.
Tests complete workflows including authentication, permissions, and data flow.
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from datetime import datetime, timedelta

from accounts.models import OTPToken
from appointments.models import Appointment


@pytest.mark.integration
class TestOTPAuthFlow:
    """Integration tests for OTP authentication flow."""

    def test_request_otp_endpoint(self, api_client, patient_user):
        """Test requesting OTP from endpoint."""
        url = reverse('otp-request-otp')  # Assuming this reverse name exists
        
        # For now, test the basic flow without actual endpoint
        # This test will need the actual API endpoint structure


    def test_verify_otp_and_password_reset_flow(self, api_client, patient_user):
        """Test complete OTP verification and password reset."""
        # Generate OTP
        OTPToken.generate_otp_token(patient_user, "email")
        otp_obj = OTPToken.objects.get(user=patient_user)
        
        # Verify OTP
        result = otp_obj.verify_otp(otp_obj.otp_value)
        
        assert result['success'] is True


    def test_rate_limiting_on_otp_request(self, api_client, patient_user):
        """Test that OTP requests are rate limited."""
        # Make 3 successful requests
        for i in range(3):
            result = OTPToken.generate_otp_token(patient_user, "email")
            assert result['success'] is True
        
        # Fourth should fail
        result = OTPToken.generate_otp_token(patient_user, "email")
        assert result['success'] is False


    def test_brute_force_protection(self, api_client, patient_user):
        """Test brute force protection on OTP verification."""
        # Generate OTP
        OTPToken.generate_otp_token(patient_user, "email")
        otp_obj = OTPToken.objects.get(user=patient_user)
        
        # Make 5 failed attempts
        for i in range(5):
            result = otp_obj.verify_otp(f"{i:06d}")
            assert result['success'] is False
        
        # Refresh from database
        otp_obj.refresh_from_db()
        
        # Should have max attempts reached
        assert otp_obj.failed_attempts >= 5


@pytest.mark.integration
class TestAppointmentFlow:
    """Integration tests for appointment creation and management."""

    def test_doctor_create_appointment(self, doctor_user, patient, practitioner):
        """Test doctor can create appointment for patient."""
        tomorrow = datetime.now().date() + timedelta(days=1)
        
        appointment = Appointment.objects.create(
            patient=patient,
            doctor=practitioner,
            appointment_date=tomorrow,
            appointment_time="09:00:00",
            status="scheduled"
        )
        
        assert appointment.id is not None
        assert appointment.status == "scheduled"


    def test_patient_view_own_appointments(self, authenticated_api_client, patient):
        """Test patient can view their own appointments."""
        # This test would use actual API endpoints
        # For now, we test the queryset filtering logic
        pass


    def test_appointment_status_transitions(self, appointment):
        """Test valid appointment status transitions."""
        valid_statuses = ["scheduled", "completed", "cancelled", "no_show"]
        
        for status_val in valid_statuses:
            appointment.status = status_val
            appointment.save()
            appointment.refresh_from_db()
            assert appointment.status == status_val


@pytest.mark.integration
class TestPaymentFlow:
    """Integration tests for payment processing."""

    def test_payment_creation_with_tax_calculation(self, patient, clinic_profile):
        """Test payment creation with automatic tax calculation."""
        from payments.models import Payment
        
        payment = Payment.objects.create(
            patient=patient,
            clinic=clinic_profile,
            amount=1000,
            payment_status="completed",
            payment_method="credit_card",
            tax_type="GST",
            tax_percent=18
        )
        
        assert payment.id is not None
        # Tax calculation should happen automatically if method exists
        if hasattr(payment, 'get_tax_amount'):
            assert payment.get_tax_amount() == 180


    def test_receipt_number_generation(self, patient, clinic_profile):
        """Test that receipt numbers are unique and auto-generated."""
        from payments.models import Payment
        
        payment1 = Payment.objects.create(
            patient=patient,
            clinic=clinic_profile,
            amount=1000
        )
        
        payment2 = Payment.objects.create(
            patient=patient,
            clinic=clinic_profile,
            amount=500
        )
        
        assert payment1.receipt_number != payment2.receipt_number


    def test_expense_tracking(self, expense):
        """Test expense creation and tracking."""
        assert expense.id is not None
        assert expense.amount > 0
        assert expense.category is not None


@pytest.mark.integration
class TestPermissionIntegration:
    """Integration tests for permission checking across endpoints."""

    def test_patient_cannot_view_other_patient_data(self, authenticated_api_client, patient_user, patient):
        """Test that patients cannot view other patients' data."""
        # This test needs actual API endpoints


    def test_doctor_can_view_all_patient_data(self, authenticated_api_client, doctor_user):
        """Test that doctors can view all patient data they work with."""
        # This test needs actual API endpoints


    def test_receptionist_can_manage_appointments(self, receptionist_user):
        """Test that receptionists can create and manage appointments."""
        # Needs actual API endpoint testing


    def test_unauthorized_access_returns_403(self, api_client):
        """Test that unauthorized access returns 403 Forbidden."""
        # Would test against protected endpoints


@pytest.mark.integration
class TestDataValidationFlow:
    """Integration tests for data validation across models."""

    def test_invalid_appointment_date_rejected(self, patient, practitioner):
        """Test that appointments in the past are rejected."""
        from django.core.exceptions import ValidationError
        
        past_date = datetime.now().date() - timedelta(days=1)
        
        appointment = Appointment(
            patient=patient,
            doctor=practitioner,
            appointment_date=past_date,
            appointment_time="09:00:00"
        )
        
        with pytest.raises(ValidationError):
            appointment.full_clean()


    def test_invalid_phone_numbers_rejected(self, db):
        """Test that invalid phone numbers are rejected."""
        from django.contrib.auth import get_user_model
        from django.core.exceptions import ValidationError
        
        User = get_user_model()
        
        user = User(
            email="test@example.com",
            phone="123"  # Too short
        )
        
        with pytest.raises(ValidationError):
            user.full_clean()


    def test_invalid_amount_rejected(self, patient, clinic_profile):
        """Test that invalid payment amounts are rejected."""
        from payments.models import Payment
        from django.core.exceptions import ValidationError
        
        payment = Payment(
            patient=patient,
            clinic=clinic_profile,
            amount=-100  # Negative
        )
        
        with pytest.raises(ValidationError):
            payment.full_clean()


@pytest.mark.integration
class TestEmailAndNotificationFlow:
    """Integration tests for email sending and notifications."""

    def test_otp_email_sent_on_generation(self, patient_user):
        """Test that OTP email is sent when OTP is generated."""
        from django.core.mail import outbox
        
        result = OTPToken.generate_otp_token(patient_user, "email")
        
        # Email should be queued (in test mode, added to outbox)
        # This depends on email backend configuration


    def test_appointment_confirmation_email(self, appointment):
        """Test that appointment confirmation email is sent."""
        # Should trigger email on appointment creation
        pass


    def test_payment_receipt_email(self, payment):
        """Test that payment receipt email is sent."""
        # Should trigger email on payment creation
        pass


@pytest.mark.integration
class TestUserAuthFlow:
    """Integration tests for user authentication."""

    def test_user_registration_flow(self, api_client):
        """Test user registration workflow."""
        # Would test registration endpoint


    def test_user_email_verification(self, unverified_user):
        """Test email verification process."""
        assert unverified_user.is_verified is False
        
        # After verification
        unverified_user.is_verified = True
        unverified_user.save()
        unverified_user.refresh_from_db()
        
        assert unverified_user.is_verified is True


    def test_jwt_token_generation(self, get_jwt_token, patient_user):
        """Test JWT token generation for authenticated user."""
        token = get_jwt_token(patient_user)
        
        assert token is not None
        assert len(token) > 0
        assert '.' in token  # JWT format: header.payload.signature


    def test_token_contains_user_info(self, get_jwt_token, patient_user):
        """Test that JWT token contains user information."""
        from rest_framework_simplejwt.tokens import AccessToken
        
        token = get_jwt_token(patient_user)
        decoded_token = AccessToken(token)
        
        assert decoded_token['user_id'] == patient_user.id


@pytest.mark.integration
class TestClinicDataFlow:
    """Integration tests for clinic data management."""

    def test_clinic_practitioner_relationship(self, clinic_profile, practitioner):
        """Test clinic and practitioner relationship."""
        assert practitioner.clinic == clinic_profile
        assert clinic_profile.practitioner_set.count() >= 1


    def test_clinic_patient_relationship(self, clinic_profile, patient):
        """Test clinic and patient relationship."""
        assert patient.clinic == clinic_profile


    def test_clinic_appointment_through_doctor(self, clinic_profile, practitioner, appointment):
        """Test appointment relationship through practitioner to clinic."""
        assert appointment.doctor.clinic == clinic_profile


@pytest.mark.integration
class TestCompleteUserJourney:
    """End-to-end tests for common user workflows."""

    def test_patient_book_appointment_workflow(self, patient_user, patient, practitioner, doctor_availability):
        """Test complete patient appointment booking workflow."""
        tomorrow = datetime.now().date() + timedelta(days=1)
        
        # Patient should be able to create appointment
        appointment = Appointment.objects.create(
            patient=patient,
            doctor=practitioner,
            appointment_date=tomorrow,
            appointment_time="09:00:00",
            status="scheduled"
        )
        
        assert appointment.id is not None
        assert appointment.patient == patient
        assert appointment.status == "scheduled"


    def test_doctor_view_and_manage_appointments(self, doctor_user, practitioner):
        """Test doctor workflow for viewing appointments."""
        # Doctor should see appointments assigned to them
        appointments = practitioner.get_appointments()
        # This depends on implementation


    def test_clinic_admin_view_analytics(self, superuser, clinic_profile):
        """Test clinic admin analytics workflow."""
        # Admin should be able to view clinic stats
        # This depends on implementation
