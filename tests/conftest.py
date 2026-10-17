"""
Pytest configuration and fixtures for SpinalCure tests.
This module provides reusable fixtures for testing the entire application.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from clinic.models import ClinicProfile, Practitioner
from patients.models import Patient
from appointments.models import DoctorAvailability, Appointment
from payments.models import Payment, Expense
from events.models import Event

User = get_user_model()


# ============================================================================
# Client Fixtures
# ============================================================================

@pytest.fixture
def client():
    """Standard Django test client."""
    return Client()


@pytest.fixture
def api_client():
    """DRF API test client."""
    return APIClient()


@pytest.fixture
def authenticated_api_client(api_client, superuser):
    """API client authenticated as superuser."""
    api_client.force_authenticate(user=superuser)
    return api_client


# ============================================================================
# User/Role Fixtures
# ============================================================================

@pytest.fixture
def superuser():
    """Create a superuser for testing."""
    return User.objects.create_user(
        email="admin@test.com",
        phone="9876543210",
        password="SecurePassword123!",
        is_superuser=True,
        is_staff=True,
        role="admin",
        is_verified=True
    )


@pytest.fixture
def doctor_user():
    """Create a doctor user for testing."""
    return User.objects.create_user(
        email="doctor@test.com",
        phone="9123456789",
        password="DoctorPass123!",
        role="doctor",
        is_verified=True
    )


@pytest.fixture
def receptionist_user():
    """Create a receptionist user for testing."""
    return User.objects.create_user(
        email="receptionist@test.com",
        phone="9111111111",
        password="ReceptionPass123!",
        role="receptionist",
        is_verified=True
    )


@pytest.fixture
def patient_user():
    """Create a patient user for testing."""
    return User.objects.create_user(
        email="patient@test.com",
        phone="9222222222",
        password="PatientPass123!",
        role="patient",
        is_verified=True
    )


@pytest.fixture
def unverified_user():
    """Create an unverified user for testing."""
    return User.objects.create_user(
        email="unverified@test.com",
        phone="9333333333",
        password="UnverifiedPass123!",
        role="patient",
        is_verified=False
    )


# ============================================================================
# JWT Token Fixtures
# ============================================================================

@pytest.fixture
def get_jwt_token():
    """Fixture to generate JWT tokens for users."""
    def _get_token(user):
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token)
    return _get_token


@pytest.fixture
def doctor_token(doctor_user, get_jwt_token):
    """JWT token for doctor user."""
    return get_jwt_token(doctor_user)


@pytest.fixture
def patient_token(patient_user, get_jwt_token):
    """JWT token for patient user."""
    return get_jwt_token(patient_user)


@pytest.fixture
def admin_token(superuser, get_jwt_token):
    """JWT token for admin user."""
    return get_jwt_token(superuser)


# ============================================================================
# Clinic Fixtures
# ============================================================================

@pytest.fixture
def clinic_profile(superuser):
    """Create a clinic profile for testing."""
    return ClinicProfile.objects.create(
        name="SpinalCure Clinic",
        owner=superuser,
        email="clinic@spinalcure.com",
        phone="9876543210",
        address="123 Spine Street, Medical City",
        city="Mumbai",
        state="Maharashtra",
        pincode="400001",
        country="India",
        gstin="27AAABZ1234K1Z1",
        upi_id="clinic@upi",
        bank_account="1234567890",
        bank_ifsc="SBIN0001234",
        specialization="Spine Surgery",
        experience_years=10,
        license_number="MED1234567"
    )


@pytest.fixture
def practitioner(clinic_profile, doctor_user):
    """Create a practitioner for testing."""
    return Practitioner.objects.create(
        clinic=clinic_profile,
        user=doctor_user,
        specialization="Orthopedic Surgery",
        license_number="LIC1234567",
        experience_years=8,
        qualification="MD, Orthopedics",
        per_session_charge=1000,
        consultation_percentage=15
    )


# ============================================================================
# Patient Fixtures
# ============================================================================

@pytest.fixture
def patient(patient_user, clinic_profile):
    """Create a patient for testing."""
    return Patient.objects.create(
        user=patient_user,
        clinic=clinic_profile,
        date_of_birth="1990-01-15",
        gender="M",
        medical_history="Previous back pain treatment",
        emergency_contact_name="John Doe",
        emergency_contact_phone="9876543210",
        blood_group="O+",
        height_cm=175,
        weight_kg=75
    )


# ============================================================================
# Appointment Fixtures
# ============================================================================

@pytest.fixture
def doctor_availability(practitioner):
    """Create doctor availability for testing."""
    from datetime import datetime, timedelta
    
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    
    return DoctorAvailability.objects.create(
        doctor=practitioner,
        date=tomorrow,
        start_time="09:00:00",
        end_time="17:00:00",
        slot_duration_minutes=30,
        break_start_time="13:00:00",
        break_end_time="14:00:00"
    )


@pytest.fixture
def appointment(patient, practitioner, doctor_availability):
    """Create an appointment for testing."""
    from datetime import datetime, timedelta
    
    tomorrow = datetime.now().date() + timedelta(days=1)
    
    return Appointment.objects.create(
        patient=patient,
        doctor=practitioner,
        appointment_date=tomorrow,
        appointment_time="09:00:00",
        notes="Follow-up consultation",
        status="scheduled",
        reference_number="APT20260306001"
    )


# ============================================================================
# Payment Fixtures
# ============================================================================

@pytest.fixture
def payment(patient, clinic_profile):
    """Create a payment for testing."""
    return Payment.objects.create(
        patient=patient,
        clinic=clinic_profile,
        amount=5000.00,
        payment_status="completed",
        payment_method="credit_card",
        transaction_id="TXN20260306001",
        receipt_number="REC20260306001",
        tax_type="GST",
        tax_percent=18,
        notes="Consultation payment"
    )


@pytest.fixture
def expense(clinic_profile):
    """Create an expense for testing."""
    return Expense.objects.create(
        clinic=clinic_profile,
        category="supplies",
        amount=500.00,
        description="Medical supplies purchase",
        vendor="Medical Supplies Inc"
    )


# ============================================================================
# Event Fixtures
# ============================================================================

@pytest.fixture
def event(clinic_profile, doctor_user):
    """Create an event for testing."""
    from datetime import datetime, timedelta
    
    start_time = datetime.now() + timedelta(days=7)
    
    return Event.objects.create(
        clinic=clinic_profile,
        title="Spinal Health Workshop",
        description="Educational workshop on spinal health",
        event_type="workshop",
        organizer=doctor_user,
        venue="Clinic Conference Room",
        start_datetime=start_time,
        end_datetime=start_time + timedelta(hours=2),
        is_published=True,
        max_participants=50
    )


# ============================================================================
# Marks/Configurations
# ============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Mark test as a unit test")
    config.addinivalue_line("markers", "integration: Mark test as an integration test")
    config.addinivalue_line("markers", "security: Mark test as a security test")
    config.addinivalue_line("markers", "otp: Mark test as OTP-related")
    config.addinivalue_line("markers", "slow: Mark test as slow-running")
