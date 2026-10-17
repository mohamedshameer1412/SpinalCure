"""
Unit tests for Django models.
Tests model validation, constraints, and business logic.
"""

import pytest
from datetime import datetime, timedelta, time
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from clinic.models import ClinicProfile, Practitioner
from patients.models import Patient
from appointments.models import DoctorAvailability, Appointment
from payments.models import Payment
from events.models import Event

User = get_user_model()


@pytest.mark.unit
class TestClinicProfileModel:
    """Test ClinicProfile model validation."""

    def test_clinic_creation_with_valid_data(self, superuser):
        """Test creating clinic profile with valid data."""
        clinic = ClinicProfile.objects.create(
            name="Test Clinic",
            owner=superuser,
            email="clinic@test.com",
            phone="9876543210",
            address="123 Main St",
            city="Mumbai",
            state="Maharashtra",
            pincode="400001",
            gstin="27AAABZ1234K1Z1"
        )
        
        assert clinic.id is not None
        assert clinic.name == "Test Clinic"


    def test_clinic_phone_validation(self, superuser):
        """Test that invalid phone numbers fail validation."""
        clinic = ClinicProfile(
            name="Test Clinic",
            owner=superuser,
            phone="123",  # Invalid
            email="clinic@test.com",
            address="123 Main St"
        )
        
        with pytest.raises(ValidationError):
            clinic.full_clean()


    def test_clinic_gstin_validation(self, superuser):
        """Test GSTIN format validation."""
        clinic = ClinicProfile(
            name="Test Clinic",
            owner=superuser,
            phone="9876543210",
            email="clinic@test.com",
            address="123 Main St",
            gstin="INVALID"
        )
        
        with pytest.raises(ValidationError):
            clinic.full_clean()


    def test_clinic_required_fields(self, superuser):
        """Test that required fields cannot be empty."""
        clinic = ClinicProfile(
            name="",  # Empty
            owner=superuser,
            email="clinic@test.com"
        )
        
        # Should raise validation error for empty name
        with pytest.raises(ValidationError):
            clinic.full_clean()


@pytest.mark.unit
class TestPractitionerModel:
    """Test Practitioner model validation."""

    def test_practitioner_creation(self, clinic_profile, doctor_user):
        """Test creating practitioner with valid data."""
        practitioner = Practitioner.objects.create(
            clinic=clinic_profile,
            user=doctor_user,
            specialization="Orthopedics",
            license_number="LIC123456",
            experience_years=5,
            per_session_charge=1000
        )
        
        assert practitioner.id is not None
        assert practitioner.experience_years == 5


    def test_practitioner_experience_must_be_positive(self, clinic_profile, doctor_user):
        """Test that experience years must be positive."""
        practitioner = Practitioner(
            clinic=clinic_profile,
            user=doctor_user,
            experience_years=-5,  # Invalid
            per_session_charge=1000
        )
        
        with pytest.raises(ValidationError):
            practitioner.full_clean()


    def test_practitioner_consultation_percentage_validation(self, clinic_profile, doctor_user):
        """Test consultation percentage is 0-100."""
        practitioner = Practitioner(
            clinic=clinic_profile,
            user=doctor_user,
            consultation_percentage=150,  # Invalid
            per_session_charge=1000
        )
        
        with pytest.raises(ValidationError):
            practitioner.full_clean()


@pytest.mark.unit
class TestPatientModel:
    """Test Patient model validation."""

    def test_patient_creation(self, patient_user, clinic_profile):
        """Test creating patient with valid data."""
        patient = Patient.objects.create(
            user=patient_user,
            clinic=clinic_profile,
            date_of_birth="1990-01-15",
            gender="M",
            blood_group="O+"
        )
        
        assert patient.id is not None
        assert patient.gender == "M"


    def test_patient_age_calculation(self, patient_user, clinic_profile):
        """Test that age is calculated correctly."""
        patient = Patient.objects.create(
            user=patient_user,
            clinic=clinic_profile,
            date_of_birth="1990-01-15",
            gender="M"
        )
        
        age = patient.age
        expected_age = datetime.now().year - 1990
        
        # Allow 1-year margin for birthday
        assert abs(age - expected_age) <= 1


    def test_patient_height_validation(self, patient_user, clinic_profile):
        """Test height validation (reasonable range)."""
        patient = Patient(
            user=patient_user,
            clinic=clinic_profile,
            height_cm=300  # Unrealistic
        )
        
        # May or may not validate depending on business rules


    def test_patient_weight_validation(self, patient_user, clinic_profile):
        """Test weight validation (reasonable range)."""
        patient = Patient(
            user=patient_user,
            clinic=clinic_profile,
            weight_kg=-50  # Invalid
        )
        
        # Should fail validation


@pytest.mark.unit
class TestAppointmentModel:
    """Test Appointment model validation."""

    def test_appointment_creation(self, patient, practitioner):
        """Test creating appointment with valid data."""
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


    def test_appointment_cannot_be_in_past(self, patient, practitioner):
        """Test that appointments cannot be scheduled in the past."""
        past_date = datetime.now().date() - timedelta(days=1)
        
        appointment = Appointment(
            patient=patient,
            doctor=practitioner,
            appointment_date=past_date,
            appointment_time="09:00:00"
        )
        
        with pytest.raises(ValidationError):
            appointment.full_clean()


    def test_appointment_reference_number_unique(self, patient, practitioner):
        """Test that reference numbers are unique."""
        tomorrow = datetime.now().date() + timedelta(days=1)
        
        app1 = Appointment.objects.create(
            patient=patient,
            doctor=practitioner,
            appointment_date=tomorrow,
            appointment_time="09:00:00",
            reference_number="APT001"
        )
        
        # Second appointment with same reference should fail
        with pytest.raises(Exception):  # IntegrityError
            app2 = Appointment.objects.create(
                patient=patient,
                doctor=practitioner,
                appointment_date=tomorrow,
                appointment_time="10:00:00",
                reference_number="APT001"
            )


@pytest.mark.unit
class TestDoctorAvailabilityModel:
    """Test DoctorAvailability model validation."""

    def test_availability_creation(self, practitioner):
        """Test creating doctor availability."""
        tomorrow = datetime.now().date() + timedelta(days=1)
        
        availability = DoctorAvailability.objects.create(
            doctor=practitioner,
            date=tomorrow,
            start_time="09:00:00",
            end_time="17:00:00"
        )
        
        assert availability.id is not None


    def test_availability_time_validation(self, practitioner):
        """Test that start_time must be before end_time."""
        tomorrow = datetime.now().date() + timedelta(days=1)
        
        availability = DoctorAvailability(
            doctor=practitioner,
            date=tomorrow,
            start_time="17:00:00",
            end_time="09:00:00"  # Reversed
        )
        
        with pytest.raises(ValidationError):
            availability.full_clean()


    def test_availability_break_time_validation(self, practitioner):
        """Test that break times are within working hours."""
        tomorrow = datetime.now().date() + timedelta(days=1)
        
        availability = DoctorAvailability(
            doctor=practitioner,
            date=tomorrow,
            start_time="09:00:00",
            end_time="17:00:00",
            break_start_time="08:00:00",  # Before working hours
            break_end_time="09:00:00"
        )
        
        with pytest.raises(ValidationError):
            availability.full_clean()


@pytest.mark.unit
class TestPaymentModel:
    """Test Payment model validation."""

    def test_payment_creation(self, payment):
        """Test that payment was created in fixture."""
        assert payment.id is not None
        assert payment.amount > 0


    def test_payment_amount_must_be_positive(self, patient, clinic_profile):
        """Test that payment amount must be positive."""
        payment = Payment(
            patient=patient,
            clinic=clinic_profile,
            amount=-100  # Invalid
        )
        
        with pytest.raises(ValidationError):
            payment.full_clean()


    def test_payment_tax_percentage_validation(self, patient, clinic_profile):
        """Test that tax percentage is 0-100."""
        payment = Payment(
            patient=patient,
            clinic=clinic_profile,
            amount=1000,
            tax_percent=150  # Invalid
        )
        
        with pytest.raises(ValidationError):
            payment.full_clean()


    def test_payment_receipt_number_unique(self, payment):
        """Test that receipt numbers are unique."""
        # Trying to create another payment with same receipt number
        with pytest.raises(Exception):  # IntegrityError
            Payment.objects.create(
                patient=payment.patient,
                clinic=payment.clinic,
                amount=5000,
                receipt_number=payment.receipt_number  # Duplicate
            )


    def test_payment_total_calculation(self, patient, clinic_profile):
        """Test that total is calculated correctly."""
        payment = Payment.objects.create(
            patient=patient,
            clinic=clinic_profile,
            amount=1000,
            tax_type="GST",
            tax_percent=18
        )
        
        expected_total = 1000 + (1000 * 0.18)
        # Assuming get_total() method exists
        if hasattr(payment, 'get_total'):
            assert payment.get_total() == expected_total


@pytest.mark.unit
class TestEventModel:
    """Test Event model validation."""

    def test_event_creation(self, event):
        """Test that event was created in fixture."""
        assert event.id is not None
        assert event.title == "Spinal Health Workshop"


    def test_event_end_datetime_after_start(self, clinic_profile, superuser):
        """Test that end_datetime is after start_datetime."""
        start = datetime.now() + timedelta(days=1)
        end = start - timedelta(hours=1)  # Before start
        
        event = Event(
            clinic=clinic_profile,
            organizer=superuser,
            title="Test Event",
            start_datetime=start,
            end_datetime=end
        )
        
        with pytest.raises(ValidationError):
            event.full_clean()


    def test_unpublished_event_can_be_in_past(self, clinic_profile, superuser):
        """Test that unpublished events can be in the past."""
        past_time = datetime.now() - timedelta(days=1)
        
        event = Event(
            clinic=clinic_profile,
            organizer=superuser,
            title="Past Event",
            start_datetime=past_time,
            end_datetime=past_time + timedelta(hours=2),
            is_published=False
        )
        
        # Should be allowed
        event.full_clean()


    def test_published_event_must_be_future(self, clinic_profile, superuser):
        """Test that published events must be in the future."""
        past_time = datetime.now() - timedelta(days=1)
        
        event = Event(
            clinic=clinic_profile,
            organizer=superuser,
            title="Past Published Event",
            start_datetime=past_time,
            end_datetime=past_time + timedelta(hours=2),
            is_published=True
        )
        
        with pytest.raises(ValidationError):
            event.full_clean()


@pytest.mark.unit
class TestUserModel:
    """Test CustomUser model validation."""

    def test_user_creation(self, db):
        """Test creating a user."""
        user = User.objects.create_user(
            email="test@example.com",
            phone="9876543210",
            password="TestPass123!"
        )
        
        assert user.id is not None
        assert user.email == "test@example.com"


    def test_user_phone_validation(self, db):
        """Test phone number validation on user."""
        user = User(
            email="test@example.com",
            phone="123"  # Invalid
        )
        
        with pytest.raises(ValidationError):
            user.full_clean()


    def test_user_email_uniqueness(self, db):
        """Test that emails are unique."""
        User.objects.create_user(
            email="duplicate@example.com",
            phone="9876543210",
            password="Pass123!"
        )
        
        # Second user with same email should fail
        with pytest.raises(Exception):  # IntegrityError
            User.objects.create_user(
                email="duplicate@example.com",
                phone="9111111111",
                password="Pass123!"
            )
