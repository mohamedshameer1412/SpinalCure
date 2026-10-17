"""Patient portal OTP, staff password reset and approval PIN flows."""
import re

import pytest
from django.core import mail
from django.urls import reverse

from tests.conftest_helpers import make_patient


def _code(message):
    return re.search(r'\b(\d{6})\b', message.body).group(1)


@pytest.mark.django_db
def test_portal_unknown_phone_gives_same_response_and_sends_nothing(client):
    resp = client.post(reverse('portal_login'), {'phone': '9000000000'})
    assert resp.status_code == 302 and resp['Location'].endswith(reverse('portal_verify'))
    assert len(mail.outbox) == 0
    resp = client.post(reverse('portal_verify'), {'otp': '123456'})  # old hard-coded code
    assert 'patient_id' not in client.session


@pytest.mark.django_db
def test_portal_login_with_emailed_code(client):
    p = make_patient(email='kavitha@example.com')
    client.post(reverse('portal_login'), {'phone': '98765-43210'})
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ['kavitha@example.com']
    client.post(reverse('portal_verify'), {'otp': _code(mail.outbox[0])})
    assert client.session['patient_id'] == str(p.pk)


@pytest.mark.django_db
def test_portal_code_locks_after_five_wrong_attempts(client):
    make_patient(email='kavitha@example.com')
    client.post(reverse('portal_login'), {'phone': '9876543210'})
    code = _code(mail.outbox[0])
    wrong = '000000' if code != '000000' else '111111'
    for _ in range(5):
        client.post(reverse('portal_verify'), {'otp': wrong})
    client.post(reverse('portal_verify'), {'otp': code})
    assert 'patient_id' not in client.session


@pytest.mark.django_db
def test_portal_login_rate_limited_per_phone(client):
    make_patient(email='kavitha@example.com')
    for _ in range(3):
        client.post(reverse('portal_login'), {'phone': '9876543210'})
    resp = client.post(reverse('portal_login'), {'phone': '9876543210'})
    assert resp.status_code == 429


def test_staff_password_reset_flow(client, make_user):
    user = make_user('doctor', email='doc@example.com')
    client.post(reverse('request_otp'), {'email': 'DOC@example.com'})
    code = _code(mail.outbox[0])
    resp = client.post(reverse('verify_otp'), {'otp': code, 'new_password': 'weak', 'confirm_password': 'weak'})
    assert resp.status_code == 200  # rejected by password validators
    resp = client.post(reverse('verify_otp'), {'otp': code, 'new_password': 'N3w-Strong-Pass!', 'confirm_password': 'N3w-Strong-Pass!'})
    assert resp.status_code == 302
    user.refresh_from_db()
    assert user.check_password('N3w-Strong-Pass!')


@pytest.mark.django_db
def test_password_reset_does_not_reveal_unknown_email(client):
    resp = client.post(reverse('request_otp'), {'email': 'nobody@example.com'})
    assert resp.status_code == 302 and len(mail.outbox) == 0


def test_login_rate_limited(client, make_user):
    make_user('doctor', email='doc@example.com')
    for _ in range(10):
        client.post(reverse('login'), {'username': 'doc@example.com', 'password': 'wrong'})
    resp = client.post(reverse('login'), {'username': 'doc@example.com', 'password': 'Str0ng-Pass-2026!'})
    assert resp.status_code == 429


def test_approval_pin_locks_after_five_wrong_attempts(users, login):
    c = login(users['receptionist'])  # receptionists can now request a PIN
    resp = c.post(reverse('session-request-pin'), {'target_name': 'X', 'action_type': 'edit'})
    assert resp.status_code == 200
    pin = re.search(r'\*\*\* (\d{4}) \*\*\*', mail.outbox[0].body).group(1)
    wrong = '0000' if pin != '0000' else '1111'
    for _ in range(5):
        c.post(reverse('session-verify-pin'), {'pin': wrong})
    resp = c.post(reverse('session-verify-pin'), {'pin': pin})
    assert resp.json()['status'] != 'ok'
