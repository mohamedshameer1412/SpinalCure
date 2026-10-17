"""
Single source of truth for roles and what each role may do.

Every view, API permission class and template check goes through `has_perm`.
Patients are not CustomUsers: they use the OTP patient portal (session-based).
"""
from django.utils.translation import gettext_lazy as _

SUPERADMIN = 'superadmin'
OWNER = 'owner'
CLINIC_ADMIN = 'clinic_admin'
DOCTOR = 'doctor'
RECEPTIONIST = 'receptionist'
STAFF = 'staff'

ROLE_CHOICES = [
    (SUPERADMIN, _('Super Admin')),
    (OWNER, _('Owner')),
    (CLINIC_ADMIN, _('Clinic Admin')),
    (DOCTOR, _('Doctor')),
    (RECEPTIONIST, _('Receptionist')),
    (STAFF, _('Staff')),
]

# Higher rank may manage lower rank, never equal or higher (superadmin excepted).
RANK = {SUPERADMIN: 100, OWNER: 90, CLINIC_ADMIN: 80, DOCTOR: 50, RECEPTIONIST: 40, STAFF: 10}

_ADMINS = {SUPERADMIN, OWNER, CLINIC_ADMIN}
_CLINICAL = _ADMINS | {DOCTOR}
_FRONT_DESK = _CLINICAL | {RECEPTIONIST}
_EVERYONE = _FRONT_DESK | {STAFF}

PERMISSIONS = {
    'dashboard_view': _EVERYONE,
    'analytics_view': _CLINICAL,
    # Patients
    'patients_view': _FRONT_DESK,
    'patients_create': _FRONT_DESK,
    'patients_edit': _FRONT_DESK,
    'patients_delete': _ADMINS,
    'patients_export': _CLINICAL,
    'clinical_view': _CLINICAL,      # sessions, history, diagnosis, plans
    'clinical_edit': _CLINICAL,
    'clinical_delete': _ADMINS,
    'reviews_manage': _ADMINS,
    # Appointments
    'appointments_view': _FRONT_DESK,
    'appointments_manage': _FRONT_DESK,
    'appointments_delete': _ADMINS,
    'availability_manage': _CLINICAL,
    # Billing
    'billing_view': _FRONT_DESK,
    'billing_create': _FRONT_DESK,
    'billing_edit': _ADMINS,
    'billing_delete': _ADMINS,
    'expenses_manage': _ADMINS,
    'finance_reports': _ADMINS,
    # Public content
    'events_manage': _CLINICAL,
    'courses_manage': _CLINICAL,
    'blog_manage': _CLINICAL,
    'site_manage': _ADMINS,          # clinic profile, practitioners, testimonials
    # Administration
    'users_manage': _ADMINS,
    'idcards_manage': _ADMINS,
    'audit_view': {SUPERADMIN, OWNER},
    'audit_revert': {SUPERADMIN},
}


def has_perm(user, perm):
    """True if an active staff user may perform `perm`. Unknown perm names raise KeyError."""
    allowed = PERMISSIONS[perm]
    if not getattr(user, 'is_authenticated', False) or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return getattr(user, 'role', None) in allowed


def rank(user):
    if user.is_superuser:
        return RANK[SUPERADMIN]
    return RANK.get(user.role, 0)


def assignable_roles(actor):
    """Roles `actor` may give to other users."""
    r = rank(actor)
    if r >= RANK[SUPERADMIN]:
        return [code for code, _l in ROLE_CHOICES]
    return [code for code, _l in ROLE_CHOICES if RANK[code] < r]


def can_manage_user(actor, target):
    """Actor may edit/deactivate target only if strictly higher ranked (superadmin may manage anyone else)."""
    if not has_perm(actor, 'users_manage') or actor.pk == target.pk:
        return False
    return rank(actor) >= RANK[SUPERADMIN] or rank(actor) > rank(target)


def perms_for(user):
    """Dict of every perm -> bool, for templates: {% if can.patients_view %}."""
    return {p: has_perm(user, p) for p in PERMISSIONS}
