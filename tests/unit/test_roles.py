"""Role permission matrix and user-management rank rules (accounts.roles)."""
import pytest

from accounts import roles
from accounts.roles import has_perm, assignable_roles, can_manage_user


@pytest.mark.parametrize('role,perm,allowed', [
    ('staff', 'patients_view', False),
    ('staff', 'dashboard_view', True),
    ('receptionist', 'patients_view', True),
    ('receptionist', 'clinical_view', False),
    ('receptionist', 'patients_export', False),
    ('receptionist', 'expenses_manage', False),
    ('receptionist', 'billing_create', True),
    ('receptionist', 'billing_edit', False),
    ('doctor', 'clinical_edit', True),
    ('doctor', 'users_manage', False),
    ('doctor', 'finance_reports', False),
    ('clinic_admin', 'users_manage', True),
    ('clinic_admin', 'audit_view', False),
    ('owner', 'audit_view', True),
    ('owner', 'audit_revert', False),
    ('superadmin', 'audit_revert', True),
])
def test_permission_matrix(users, role, perm, allowed):
    assert has_perm(users[role], perm) is allowed


def test_inactive_and_anonymous_have_nothing(users):
    from django.contrib.auth.models import AnonymousUser
    u = users['owner']
    u.is_active = False
    assert not any(has_perm(u, p) for p in roles.PERMISSIONS)
    assert not any(has_perm(AnonymousUser(), p) for p in roles.PERMISSIONS)


def test_is_staff_flag_grants_nothing(make_user):
    # Old code turned is_staff users into doctors and let them manage users.
    u = make_user('receptionist', is_staff=True)
    u.refresh_from_db()
    assert u.role == 'receptionist'
    assert not has_perm(u, 'users_manage')


def test_unknown_permission_is_an_error(users):
    with pytest.raises(KeyError):
        has_perm(users['owner'], 'no_such_perm')


def test_assignable_roles_are_strictly_lower(users):
    assert set(assignable_roles(users['clinic_admin'])) == {'doctor', 'receptionist', 'staff'}
    assert 'owner' not in assignable_roles(users['owner'])
    assert 'clinic_admin' in assignable_roles(users['owner'])
    assert 'superadmin' in assignable_roles(users['superadmin'])
    assert assignable_roles(users['doctor']) == ['receptionist', 'staff']  # rank only; users_manage still required


def test_can_manage_user(users):
    assert can_manage_user(users['clinic_admin'], users['doctor'])
    assert not can_manage_user(users['clinic_admin'], users['owner'])
    assert not can_manage_user(users['clinic_admin'], users['clinic_admin'])
    assert not can_manage_user(users['doctor'], users['staff'])  # no users_manage
    assert can_manage_user(users['owner'], users['clinic_admin'])
    assert not can_manage_user(users['owner'], users['owner'])  # never yourself
