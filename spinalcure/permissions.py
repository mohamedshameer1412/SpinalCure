"""
DRF permission classes. All role logic lives in accounts.roles.
"""
from rest_framework.permissions import BasePermission, IsAuthenticated, SAFE_METHODS  # noqa: F401 (re-exported)

from accounts.roles import has_perm, PERMISSIONS


def ReadWritePerm(read, write, delete=None):
    """Different perms for safe methods, writes and DELETE. read=None means public reads."""
    for p in (read, write, delete):
        if p:
            PERMISSIONS[p]

    class _ReadWritePerm(BasePermission):
        message = 'You do not have permission to perform this action.'

        def has_permission(self, request, view):
            if request.method in SAFE_METHODS:
                return read is None or has_perm(request.user, read)
            if request.method == 'DELETE' and delete:
                return has_perm(request.user, delete)
            return has_perm(request.user, write)

    return _ReadWritePerm


class IsSuperAdmin(BasePermission):
    message = 'Only Super Admins can access this resource.'

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.is_active and (u.is_superuser or u.role == 'superadmin'))


class IsDoctor(BasePermission):
    """Clinical access: admins and doctors."""
    message = 'Only Doctors and Admins can access this resource.'

    def has_permission(self, request, view):
        return has_perm(request.user, 'clinical_view')


class IsReceptionist(BasePermission):
    """Front-desk access: admins, doctors and receptionists."""
    message = 'Only clinic staff can access this resource.'

    def has_permission(self, request, view):
        return has_perm(request.user, 'patients_view')


class IsClinicAdmin(BasePermission):
    message = 'Only clinic administrators can access this resource.'

    def has_permission(self, request, view):
        return has_perm(request.user, 'site_manage')

    def has_object_permission(self, request, view, obj):
        return has_perm(request.user, 'site_manage')
