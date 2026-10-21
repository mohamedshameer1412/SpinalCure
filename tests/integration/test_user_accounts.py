"""Account admin: superuser-only delete, and creating a practitioner profile straight from an account."""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from clinic.models import ClinicProfile, Practitioner

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def clinic(db):
    return ClinicProfile.objects.create(name='C', address='a', phone='9876543210', email='c@x.com')


def login(client, role, **kw):
    u = User.objects.create_user(username=role + 'u', email=f'{role}@x.com', password='Str0ng!pass9', role=role, **kw)
    client.force_login(u)
    return u


def test_only_a_superadmin_can_delete(client, clinic):
    victim = User.objects.create_user(username='v', email='v@x.com', password='Str0ng!pass9', role='staff')
    login(client, 'clinicadmin')
    client.post(reverse('admin_user_delete', args=[victim.pk]))
    assert User.objects.filter(pk=victim.pk).exists()


def test_superadmin_deletes_others_but_not_self(client, clinic):
    victim = User.objects.create_user(username='v', email='v@x.com', password='Str0ng!pass9', role='staff')
    me = login(client, 'superadmin', is_superuser=True)
    client.post(reverse('admin_user_delete', args=[victim.pk]))
    assert not User.objects.filter(pk=victim.pk).exists()
    client.post(reverse('admin_user_delete', args=[me.pk]))
    assert User.objects.filter(pk=me.pk).exists()


def test_account_creates_a_linked_practitioner_without_retyping(client, clinic):
    login(client, 'superadmin', is_superuser=True)
    r = client.post(reverse('admin_user_create'), {
        'username': 'dr.new', 'first_name': 'Asha', 'last_name': 'Rao', 'email': 'asha@x.com', 'password': 'Str0ng!pass9',
        'role': 'staff', 'language': 'en', 'designation': 'Acupuncturist', 'phone': '9876543211',
        'practitioner_mode': 'create', 'specialization': 'Back pain', 'experience_years': '4'})
    assert r.status_code == 302, r.context['form'].errors
    pr = Practitioner.objects.get(user__username='dr.new')
    assert (pr.name, pr.email, pr.phone, pr.title, pr.specialization, pr.experience_years) == (
        'Asha Rao', 'asha@x.com', '9876543211', 'Acupuncturist', 'Back pain', 4)


def test_linking_an_existing_practitioner_keeps_its_data(client, clinic):
    login(client, 'superadmin', is_superuser=True)
    existing = Practitioner.objects.create(name='Dr Existing', email='old@x.com')
    client.post(reverse('admin_user_create'), {
        'username': 'link', 'first_name': 'New', 'last_name': 'Name', 'email': 'new@x.com', 'password': 'Str0ng!pass9',
        'role': 'staff', 'language': 'en', 'designation': 'Doctor', 'practitioner_mode': 'link', 'link_practitioner': str(existing.pk)})
    existing.refresh_from_db()
    assert existing.user.username == 'link' and existing.name == 'Dr Existing' and existing.email == 'old@x.com'


def test_deleting_a_user_who_has_notifications(client, clinic):
    from notifications.models import Notification
    victim = User.objects.create_user(username='n', email='n@x.com', password='Str0ng!pass9', role='staff')
    Notification.objects.create(user=victim, event_type='appointment_booked', title='Hi')
    login(client, 'superadmin', is_superuser=True)
    client.post(reverse('admin_user_delete', args=[victim.pk]))
    assert not User.objects.filter(pk=victim.pk).exists() and Notification.objects.count() == 0
