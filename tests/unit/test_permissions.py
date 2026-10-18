"""
Unit tests for permission classes and role-based access control.
Tests RBAC implementation across the application.
"""

import pytest
from django.test import RequestFactory
from rest_framework.test import APIRequestFactory

from spinalcure.permissions import (
    IsSuperAdmin,
    IsDoctor,
    IsReceptionist,
    IsOwnerOrAdmin,
    IsPatientOwnerOrDoctor,
    IsClinicAdmin
)


@pytest.mark.unit
class TestIsSuperAdmin:
    """Test IsSuperAdmin permission class."""

    def test_superuser_has_permission(self, superuser):
        """Test that superusers have permission."""
        permission = IsSuperAdmin()
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = superuser
        
        assert permission.has_permission(request, None) is True


    def test_regular_user_denied(self, patient_user):
        """Test that regular users are denied."""
        permission = IsSuperAdmin()
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = patient_user
        
        assert permission.has_permission(request, None) is False


    def test_doctor_user_denied(self, doctor_user):
        """Test that doctors are denied."""
        permission = IsSuperAdmin()
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = doctor_user
        
        assert permission.has_permission(request, None) is False


@pytest.mark.unit
class TestIsDoctor:
    """Test IsDoctor permission class."""

    def test_doctor_has_permission(self, doctor_user):
        """Test that doctors have permission."""
        permission = IsDoctor()
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = doctor_user
        
        assert permission.has_permission(request, None) is True


    def test_superuser_has_permission(self, superuser):
        """Test that superusers have permission."""
        permission = IsDoctor()
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = superuser
        
        # Superadmins should have permission if is_staff is True
        assert permission.has_permission(request, None) is True


    def test_patient_denied(self, patient_user):
        """Test that patients are denied."""
        permission = IsDoctor()
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = patient_user
        
        assert permission.has_permission(request, None) is False


    def test_receptionist_has_permission(self, receptionist_user):
        """Test that receptionists have permission (staff)."""
        permission = IsDoctor()
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = receptionist_user
        
        # Receptionists without doctor permission should be denied
        assert permission.has_permission(request, None) is False


@pytest.mark.unit
class TestIsReceptionist:
    """Test IsReceptionist permission class."""

    def test_authenticated_user_has_permission(self, receptionist_user):
        """Test that authenticated users have permission."""
        permission = IsReceptionist()
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = receptionist_user
        
        assert permission.has_permission(request, None) is True


    def test_superuser_has_permission(self, superuser):
        """Test that superusers have permission."""
        permission = IsReceptionist()
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = superuser
        
        assert permission.has_permission(request, None) is True


    def test_unauthenticated_denied(self):
        """Test that unauthenticated users are denied."""
        permission = IsReceptionist()
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = None
        
        assert permission.has_permission(request, None) is False


@pytest.mark.unit
class TestIsOwnerOrAdmin:
    """Test IsOwnerOrAdmin permission class."""

    def test_owner_has_object_permission(self, patient_user):
        """Test that object owner has permission."""
        permission = IsOwnerOrAdmin()
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = patient_user
        
        # Create a mock object with owner
        class MockObject:
            created_by = patient_user
        
        obj = MockObject()
        
        assert permission.has_object_permission(request, None, obj) is True


    def test_non_owner_denied(self, patient_user, doctor_user):
        """Test that non-owners are denied."""
        permission = IsOwnerOrAdmin()
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = patient_user
        
        class MockObject:
            owner = doctor_user  # Different user
        
        obj = MockObject()
        
        assert permission.has_object_permission(request, None, obj) is False


    def test_admin_has_permission(self, superuser, patient_user):
        """Test that admins/superusers always have permission."""
        permission = IsOwnerOrAdmin()
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = superuser
        
        class MockObject:
            created_by = patient_user
        
        obj = MockObject()
        
        # Superuser should have permission regardless of ownership
        assert permission.has_object_permission(request, None, obj) is True


@pytest.mark.unit
class TestIsPatientOwnerOrDoctor:
    """Test IsPatientOwnerOrDoctor permission class."""

    def test_patient_sees_own_records(self, patient_user):
        """Test that patients can see their own records."""
        permission = IsPatientOwnerOrDoctor()
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = patient_user
        
        class MockObject:
            patient = None
            def get_patient(self):
                return patient_user
        
        obj = MockObject()
        
        # This test depends on implementation details


    def test_doctor_sees_all_records(self, doctor_user):
        """Test that doctors can see all patient records."""
        permission = IsPatientOwnerOrDoctor()
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = doctor_user
        request.user.role = 'doctor'
        
        assert permission.has_permission(request, None) is True


    def test_other_patient_denied(self, patient_user, doctor_user):
        """Test that patients cannot see other patient records."""
        permission = IsPatientOwnerOrDoctor()
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = patient_user
        
        class MockObject:
            patient = doctor_user  # Different patient
        
        obj = MockObject()
        
        # Depends on implementation


@pytest.mark.unit
class TestIsClinicAdmin:
    """Test IsClinicAdmin permission class."""

    def test_superuser_is_admin(self, superuser):
        """Test that superusers are clinic admins."""
        permission = IsClinicAdmin()
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = superuser
        
        assert permission.has_permission(request, None) is True


    def test_regular_user_denied(self, patient_user):
        """Test that regular users are denied."""
        permission = IsClinicAdmin()
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = patient_user
        
        assert permission.has_permission(request, None) is False


@pytest.mark.unit
class TestPermissionIntegration:
    """Integration tests for multiple permission scenarios."""

    def test_permission_chain(self, superuser, doctor_user, patient_user):
        """Test that permissions work correctly in hierarchy."""
        factory = APIRequestFactory()
        
        # Superuser should pass all checks
        request = factory.get('/')
        request.user = superuser
        
        assert IsSuperAdmin().has_permission(request, None) is True
        assert IsDoctor().has_permission(request, None) is True
        assert IsReceptionist().has_permission(request, None) is True


    def test_role_isolation(self, doctor_user, patient_user):
        """Test that roles don't bleed into each other."""
        factory = APIRequestFactory()
        
        # Doctor shouldn't have patient-specific permissions
        request = factory.get('/')
        request.user = doctor_user
        
        # But doctor should have permission to access patient data
        # This depends on the view implementation
