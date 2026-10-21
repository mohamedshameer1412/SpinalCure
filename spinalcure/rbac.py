"""
Central role -> capability matrix.

Roles map to accounts.CustomUser.role. Owner / Staff / ClinicAdmin are organisational roles and do
NOT imply clinical access: clinical data is limited to doctors and super admins. Patients are not
CustomUser accounts; they authenticate through the patient portal session.

`is_staff` (Django admin flag) deliberately grants nothing here.
"""
from django.utils.translation import gettext
from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect

SUPERADMIN, CLINICADMIN, OWNER, DOCTOR, RECEPTIONIST, STAFF = (
    'superadmin', 'clinicadmin', 'owner', 'doctor', 'receptionist', 'staff')

MANAGEMENT = {SUPERADMIN, CLINICADMIN, OWNER}

CAPABILITIES = {
    'patients.view': MANAGEMENT | {DOCTOR, RECEPTIONIST},
    'patients.edit': MANAGEMENT | {DOCTOR, RECEPTIONIST},
    'clinical.view': {SUPERADMIN, DOCTOR},
    'clinical.edit': {SUPERADMIN, DOCTOR},
    'appointments.manage': MANAGEMENT | {DOCTOR, RECEPTIONIST},
    'schedule.manage': MANAGEMENT | {DOCTOR},
    'billing.view': MANAGEMENT | {DOCTOR, RECEPTIONIST},
    'billing.manage': MANAGEMENT | {RECEPTIONIST},
    'billing.refund': MANAGEMENT,
    'packages.manage': MANAGEMENT,
    'expenses.manage': MANAGEMENT,
    'reports.view': MANAGEMENT,
    'users.manage': {SUPERADMIN, CLINICADMIN},
    'idcards.manage': MANAGEMENT,
    'events.manage': MANAGEMENT,
    'events.registrations': MANAGEMENT | {RECEPTIONIST},
    'website.manage': MANAGEMENT,
    'reviews.manage': MANAGEMENT | {DOCTOR},
    'audit.view': MANAGEMENT,
    'notifications.admin': MANAGEMENT,
}


def has_capability(user, capability):
    if not getattr(user, 'is_authenticated', False) or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return user.role in CAPABILITIES.get(capability, set())


def require_capability(capability):
    """View decorator: login + capability. HTML requests get a flash + redirect, XHR/API get 403 JSON."""
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())
            if has_capability(request.user, capability):
                return view(request, *args, **kwargs)
            wants_json = (request.headers.get('x-requested-with') == 'XMLHttpRequest'
                          or 'application/json' in request.headers.get('Accept', ''))
            if wants_json:
                return JsonResponse({'status': 'error', 'message': gettext('Permission denied.')}, status=403)
            messages.error(request, gettext('You do not have permission to view this page.'))
            return redirect('dashboard')
        return wrapper
    return decorator


def capability_permission(capability):
    """Build a DRF permission class for a capability."""
    from rest_framework.permissions import BasePermission

    class _Permission(BasePermission):
        message = 'Permission denied.'

        def has_permission(self, request, view):
            return has_capability(request.user, capability)

    _Permission.__name__ = f'Has_{capability.replace(".", "_")}'
    return _Permission


def capability_rw_permission(read, write):
    """DRF permission: `read` capability for safe methods, `write` capability otherwise."""
    from rest_framework.permissions import SAFE_METHODS, BasePermission

    class _Permission(BasePermission):
        message = 'Permission denied.'

        def has_permission(self, request, view):
            return has_capability(request.user, read if request.method in SAFE_METHODS else write)

    _Permission.__name__ = f'Rw_{read.replace(".", "_")}_{write.replace(".", "_")}'
    return _Permission
