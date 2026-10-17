"""
Custom permission classes for SpinalCure API.
"""
from rest_framework.permissions import BasePermission, IsAuthenticated


class IsSuperAdmin(BasePermission):
    """
    Allows access only to super admin users.
    """
    message = 'Only Super Admins can access this resource.'

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.is_superuser or request.user.role == 'superadmin')
        )


class IsDoctor(BasePermission):
    """
    Allows access to doctors and super admins.
    """
    message = 'Only Doctors and Admins can access this resource.'

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.is_superuser or request.user.role in ['superadmin', 'doctor'])
        )


class IsReceptionist(BasePermission):
    """
    Allows access to receptionists, doctors, and super admins.
    """
    message = 'Only authenticated staff can access this resource.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class IsOwnerOrAdmin(BasePermission):
    """
    Allows access only if user is the object owner or admin.
    """
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'created_by'):
            return obj.created_by == request.user or request.user.is_superuser
        return request.user.is_superuser


class IsPatientOwnerOrDoctor(BasePermission):
    """
    Allows patients to view their own data and doctors to view all.
    """
    def has_object_permission(self, request, view, obj):
        # Doctors and admins can access all
        if request.user.role in ['superadmin', 'doctor']:
            return True
        # Patients can only access their own data
        if hasattr(obj, 'patient'):
            return obj.patient.id == request.user.id
        elif hasattr(obj, 'id'):
            return obj.id == request.user.id
        return False


class IsClinicAdmin(BasePermission):
    """
    Allows only clinic admin to modify clinic settings.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.role == 'superadmin'
        )

    def has_object_permission(self, request, view, obj):
        return request.user.role == 'superadmin'


class SafeMethodsOnly(BasePermission):
    """
    Allows POST only, but blocks PUT/PATCH/DELETE.
    """
    def has_permission(self, request, view):
        if request.method == 'POST':
            return True
        return bool(request.user and request.user.is_authenticated and request.user.role == 'superadmin')
