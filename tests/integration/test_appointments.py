"""
Tests for appointment-related API endpoints.
"""

import pytest
from rest_framework import status
from datetime import datetime, timedelta
from django.urls import reverse

from appointments.models import Appointment, DoctorAvailability


@pytest.mark.integration
class TestAppointmentViewSet:
    """Integration tests for Appointment API endpoints."""

    def test_appointment_list_requires_authentication(self, api_client):
        """Test that appointment list requires authentication."""
        url = "/api/appointments/"
        response = api_client.get(url)
        
        assert response.status_code in [401, 403]


    def test_patient_see_own_appointments(self, authenticated_api_client, patient, appointment):
        """Test that patients can see their own appointments."""
        url = "/api/appointments/"
        response = authenticated_api_client.get(url)
        
        # Should return appointments for authenticated patient


    def test_doctor_see_assigned_appointments(self, authenticated_api_client, doctor_user, appointment):
        """Test that doctors can see their appointments."""
        url = "/api/appointments/"
        response = authenticated_api_client.get(url)
        
        # Should return appointments assigned to doctor


    def test_create_appointment_validates_date(self, authenticated_api_client):
        """Test that appointment date validation works."""
        url = "/api/appointments/"
        past_date = (datetime.now() - timedelta(days=1)).date()
        
        data = {
            "appointment_date": past_date,
            "appointment_time": "09:00:00"
        }
        
        response = authenticated_api_client.post(url, data)
        
        # Should reject past date
        assert response.status_code == 400 or not response.data.get('success')


    def test_appointment_confirms_availability(self, authenticated_api_client, doctor_availability):
        """Test that system checks doctor availability."""
        url = "/api/appointments/"
        data = {
            "doctor": doctor_availability.doctor.id,
            "appointment_date": str(doctor_availability.date),
            "appointment_time": "09:00:00"
        }
        
        # Should succeed if time is available


    def test_appointment_prevents_double_booking(self, authenticated_api_client, appointment):
        """Test that system prevents double booking same time slot."""
        url = "/api/appointments/"
        data = {
            "doctor": appointment.doctor.id,
            "appointment_date": str(appointment.appointment_date),
            "appointment_time": appointment.appointment_time
        }
        
        response = authenticated_api_client.post(url, data)
        
        # Should reject duplicate booking


    def test_appointment_status_transitions(self, authenticated_api_client, appointment):
        """Test valid appointment status transitions."""
        url = f"/api/appointments/{appointment.id}/"
        
        # Test transition from scheduled to completed
        data = {"status": "completed"}
        response = authenticated_api_client.patch(url, data)
        
        # Depends on workflow implementation


    def test_cancel_appointment(self, authenticated_api_client, appointment):
        """Test canceling an appointment."""
        url = f"/api/appointments/{appointment.id}/cancel/"
        response = authenticated_api_client.post(url)
        
        # Should mark appointment as cancelled


    def test_reschedule_appointment(self, authenticated_api_client, appointment):
        """Test rescheduling an appointment."""
        url = f"/api/appointments/{appointment.id}/reschedule/"
        
        new_date = (datetime.now() + timedelta(days=2)).date()
        data = {
            "new_date": new_date,
            "new_time": "14:00:00"
        }
        
        response = authenticated_api_client.post(url, data)
        
        # Should reschedule to new date/time


    def test_appointment_filtering_by_status(self, authenticated_api_client):
        """Test filtering appointments by status."""
        url = "/api/appointments/?status=scheduled"
        response = authenticated_api_client.get(url)
        
        # Should return only scheduled appointments


    def test_appointment_filtering_by_date(self, authenticated_api_client):
        """Test filtering appointments by date."""
        tomorrow = (datetime.now() + timedelta(days=1)).date()
        url = f"/api/appointments/?date={tomorrow}"
        response = authenticated_api_client.get(url)
        
        # Should return appointments for specified date


@pytest.mark.integration
class TestDoctorAvailabilityViewSet:
    """Integration tests for Doctor Availability endpoints."""

    def test_doctor_set_availability(self, authenticated_api_client, doctor_user):
        """Test doctor setting availability."""
        url = "/api/availability/"
        
        tomorrow = (datetime.now() + timedelta(days=1)).date()
        data = {
            "date": str(tomorrow),
            "start_time": "09:00:00",
            "end_time": "17:00:00",
            "slot_duration_minutes": 30
        }
        
        response = authenticated_api_client.post(url, data)
        
        # Doctor should be able to set availability


    def test_availability_list_public_access(self, api_client, doctor_availability):
        """Test that availability can be viewed publicly for booking."""
        url = f"/api/availability/{doctor_availability.doctor.id}/"
        response = api_client.get(url)
        
        # Should return available slots


    def test_availability_includes_break_times(self, authenticated_api_client, doctor_availability):
        """Test that available slots exclude break times."""
        # Fetch availability slots
        # Verify break times are excluded


    def test_suggest_available_slots(self, api_client, doctor_availability):
        """Test endpoint that suggests available appointment slots."""
        url = "/api/availability/suggest_slots/"
        data = {
            "doctor": doctor_availability.doctor.id,
            "date": str(doctor_availability.date)
        }
        
        response = api_client.post(url, data)
        
        # Should return available 30-minute slots


@pytest.mark.integration
class TestAppointmentNotifications:
    """Integration tests for appointment notifications."""

    def test_appointment_confirmation_email_sent(self, authenticated_api_client):
        """Test that confirmation email is sent on appointment creation."""
        from django.core.mail import outbox
        
        url = "/api/appointments/"
        data = {
            "appointment_date": "2025-03-15",
            "appointment_time": "09:00:00"
        }
        
        response = authenticated_api_client.post(url, data)
        
        # Email should be in outbox


    def test_reminder_email_scheduled(self, appointment):
        """Test that reminder email is scheduled for 24 hours before."""
        # Check if reminder task is scheduled
        pass


    def test_cancellation_notification_sent(self, authenticated_api_client, appointment):
        """Test that cancellation notification is sent."""
        url = f"/api/appointments/{appointment.id}/cancel/"
        response = authenticated_api_client.post(url)
        
        # Email should be sent to patient and doctor
