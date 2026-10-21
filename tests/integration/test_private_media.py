"""Patient photos, staff photos and receipts live outside the public media folder and need a signed-in, permitted user."""
import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import Client
from PIL import Image

from patients.models import Patient
from payments.models import Expense

User = get_user_model()
pytestmark = pytest.mark.django_db


def png():
    buf = io.BytesIO()
    Image.new('RGB', (30, 30), (20, 100, 60)).save(buf, 'PNG')
    return buf.getvalue()


def user(role):
    return User.objects.create_user(username=f'pm-{role}', email=f'pm-{role}@x.com', password='x-Str0ng-pass!', role=role)


@pytest.fixture
def files():
    p = Patient.objects.create(name='Photo Patient', phone='9000000201', gender='F')
    p.photo.save('face.png', ContentFile(png()))
    e = Expense.objects.create(title='Needles', amount=100, category='supplies', expense_date='2026-01-01')
    e.receipt.save('bill.png', ContentFile(png()))
    return p, e


def test_files_are_served_by_django_not_from_the_public_folder(files):
    p, e = files
    assert p.photo.url.startswith('/private-media/patients/') and e.receipt.url.startswith('/private-media/expenses/')
    assert 'face' not in p.photo.name                                          # random name, original not guessable


def test_signed_out_visitors_get_404(files):
    p, e = files
    assert Client().get(p.photo.url).status_code == 404 and Client().get(e.receipt.url).status_code == 404


@pytest.mark.parametrize('role, patients_ok, expenses_ok', [
    ('receptionist', True, False), ('doctor', True, False), ('owner', True, True), ('staff', False, False)])
def test_access_follows_the_role(files, role, patients_ok, expenses_ok):
    p, e = files
    c = Client()
    c.force_login(user(role))
    assert (c.get(p.photo.url).status_code == 200) is patients_ok
    assert (c.get(e.receipt.url).status_code == 200) is expenses_ok


def test_private_files_have_safe_headers_and_no_path_traversal(files):
    p, _ = files
    c = Client()
    c.force_login(user('owner'))
    r = c.get(p.photo.url)
    assert r['X-Content-Type-Options'] == 'nosniff' and r['Content-Type'] == 'image/png' and 'private' in r['Cache-Control']
    for bad in ('/private-media/../settings/base.py', '/private-media/patients/../../manage.py', '/private-media/secrets/x.png'):
        assert c.get(bad).status_code == 404
