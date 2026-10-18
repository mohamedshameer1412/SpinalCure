"""
Pytest configuration and fixtures for SpinalCure tests.
This module provides reusable fixtures for testing the entire application.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from clinic.models import ClinicProfile

User = get_user_model()


@pytest.fixture(autouse=True)
def _enable_db(db):
    """Every test in this suite touches the database."""


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
        username="admin",
        email="admin@test.com",
        phone="9876543210",
        password="SecurePassword123!",
        is_superuser=True,
        is_staff=True,
        role="superadmin",
        is_verified=True
    )


@pytest.fixture
def doctor_user():
    """Create a doctor user for testing."""
    return User.objects.create_user(
        username="doctor",
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
        username="receptionist",
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
        username="patient",
        email="patient@test.com",
        phone="9222222222",
        password="PatientPass123!",
        role="receptionist",
        is_verified=True
    )


@pytest.fixture
def unverified_user():
    """Create an unverified user for testing."""
    return User.objects.create_user(
        username="unverified",
        email="unverified@test.com",
        phone="9333333333",
        password="UnverifiedPass123!",
        role="receptionist",
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
        email="clinic@spinalcure.com",
        phone="9876543210",
        address="123 Spine Street, Medical City, Mumbai, Maharashtra 400001",
        gstin="27AAABZ1234K1Z1",
        upi_id="clinic@upi",
        bank_account="1234567890",
        bank_ifsc="SBIN0001234",
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
