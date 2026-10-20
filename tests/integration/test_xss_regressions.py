"""Stored values written by one staff member must never reach another member's page as live markup."""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from patients.models import AcupunctureDiagnosis, Patient

pytestmark = pytest.mark.django_db
PAYLOAD = '"><img src=x onerror=alert(1)>'


def test_diagnosis_values_are_not_rendered_raw():
    admin = get_user_model().objects.create_user(username='a', email='a@x.com', password='x-Str0ng-pass!', role='superadmin',
                                                 is_superuser=True, is_staff=True)
    p = Patient.objects.create(name='X', phone='+919000000009')
    AcupunctureDiagnosis.objects.create(patient=p, diagnosis_data={'note': PAYLOAD})
    c = Client()
    c.force_login(admin)
    html = c.get(reverse('patient-detail', args=[p.pk])).content.decode()
    assert PAYLOAD not in html and '<img src=x onerror' not in html
