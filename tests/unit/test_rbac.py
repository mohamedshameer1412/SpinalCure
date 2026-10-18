"""Capability matrix, API permissions and user-admin hardening."""
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from accounts.models import StaffProfile
from clinic.models import ClinicProfile
from spinalcure.rbac import has_capability

User = get_user_model()


def mk(role, **kw):
    return User.objects.create_user(username=f'u_{role}', email=f'{role}@example.com', password='Str0ng!pass9', role=role, **kw)


@pytest.mark.parametrize('role,cap,allowed', [
    ('receptionist', 'patients.view', True),
    ('receptionist', 'appointments.manage', True),
    ('receptionist', 'clinical.view', False),
    ('receptionist', 'reports.view', False),
    ('doctor', 'clinical.edit', True),
    ('doctor', 'users.manage', False),
    ('owner', 'clinical.view', False),   # organisational role, not clinical
    ('owner', 'idcards.manage', True),
    ('clinicadmin', 'users.manage', True),
    ('staff', 'patients.view', False),
    ('staff', 'billing.view', False),
])
def test_matrix(role, cap, allowed):
    assert has_capability(mk(role), cap) is allowed


def test_is_staff_flag_grants_nothing():
    assert not has_capability(mk('staff', is_staff=True), 'patients.view')


def test_inactive_user_has_no_capabilities():
    assert not has_capability(mk('doctor', is_active=False), 'patients.view')


def test_receptionist_can_use_appointments_api_but_not_session_api():
    api = APIClient()
    api.force_authenticate(mk('receptionist'))
    assert api.get('/api/appointments/').status_code == 200
    assert api.get('/api/sessions/').status_code == 403
    assert api.get('/api/payments/').status_code == 200
    assert api.post('/api/payments/', {}, format='json').status_code in (400, 200, 201)


def test_staff_role_is_blocked_from_patient_api():
    api = APIClient()
    api.force_authenticate(mk('staff'))
    assert api.get('/api/patients/').status_code == 403


def test_session_pdf_requires_clinical_capability(client):
    client.force_login(mk('receptionist'))
    resp = client.get('/en/patients/sessions/00000000-0000-0000-0000-000000000000/pdf/')
    assert resp.status_code in (302, 403, 404)
    assert resp.status_code != 200


@pytest.fixture
def clinic(db):
    return ClinicProfile.objects.create(name='Test Clinic', address='1 Main St', phone='9876543210')


def test_user_toggle_requires_post_and_capability(client):
    admin = mk('clinicadmin')
    target = User.objects.create_user(username='t', email='t@example.com', password='Str0ng!pass9', role='doctor')
    client.force_login(mk('receptionist'))
    assert client.post(reverse('admin_user_toggle', args=[target.pk])).status_code == 302
    target.refresh_from_db(); assert target.is_active  # blocked: receptionist cannot manage users
    client.force_login(admin)
    assert client.get(reverse('admin_user_toggle', args=[target.pk])).status_code == 405  # GET no longer mutates


def test_staff_profile_ids_are_sequential_and_immutable(clinic):
    from datetime import date
    a = StaffProfile.objects.create(user=mk('staff'), clinic=clinic, designation='Therapist', joined_on=date.today())
    o = StaffProfile.objects.create(user=mk('owner'), clinic=clinic, designation='Founder', joined_on=date.today())
    assert a.employee_id == 'STF-0001' and o.employee_id == 'OWN-0001'
    a.employee_id = 'STF-9999'
    with pytest.raises(ValueError):
        a.save()
