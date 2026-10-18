"""Regression tests for Phase 1 account/OTP fixes. Run against the real models."""
from datetime import datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import OTPToken
from spinalcure.validators import validate_not_in_future, validate_not_in_past, validate_phone_number

User = get_user_model()


def make_user(username, role='receptionist', **extra):
    return User.objects.create_user(
        username=username, email=f'{username}@example.com', password='Pass12345!x', role=role, **extra
    )


def test_staff_flag_does_not_promote_receptionist_to_doctor():
    user = make_user('recep', role='receptionist', is_staff=True)
    user.refresh_from_db()
    assert user.role == 'receptionist'


def test_superuser_is_always_superadmin():
    user = make_user('root', role='doctor', is_superuser=True)
    user.refresh_from_db()
    assert user.role == 'superadmin'


def test_otp_roundtrip_and_no_plaintext_storage():
    user = make_user('alice')
    token, code, _created = OTPToken.generate_otp_token(user)
    token.refresh_from_db()
    assert token.otp_value == ''  # code is never persisted
    ok, used, err = OTPToken.verify_otp(user, code)
    assert ok and err is None and used.is_used


def test_otp_rejects_wrong_code_and_locks_after_five_failures():
    user = make_user('bob')
    _token, code, _ = OTPToken.generate_otp_token(user)
    wrong = '000000' if code != '000000' else '111111'
    for _i in range(5):
        ok, _t, _e = OTPToken.verify_otp(user, wrong)
        assert not ok
    ok, _t, _e = OTPToken.verify_otp(user, code)  # even the right code is now dead
    assert not ok


def test_otp_roundtrip_is_independent_of_creation_second(monkeypatch):
    """Old code used created_at.second as the TOTP interval (0 => ZeroDivisionError)."""
    user = make_user('carol')
    _token, code, _ = OTPToken.generate_otp_token(user)
    OTPToken.objects.filter(user=user).update(created_at=timezone.now().replace(second=0))
    ok, _t, _e = OTPToken.verify_otp(user, code)
    assert ok


def test_request_otp_response_does_not_reveal_account_existence():
    client = APIClient()
    make_user('dave')
    known = client.post('/api/auth/request_otp/', {'email': 'dave@example.com'}, format='json')
    unknown = client.post('/api/auth/request_otp/', {'email': 'nobody@example.com'}, format='json')
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert len(mail.outbox) == 1  # only the real account got an email


def test_verify_otp_unknown_account_gives_generic_error():
    client = APIClient()
    resp = client.post('/api/auth/verify_otp/', {'email': 'nobody@example.com', 'otp': '123456'}, format='json')
    assert resp.status_code == 400
    assert 'No account' not in str(resp.json())


def test_validators_accept_datetimes_and_formatted_phones():
    validate_not_in_future(timezone.now() - timedelta(days=1))
    validate_not_in_past(timezone.now() + timedelta(days=1))
    with pytest.raises(ValidationError):
        validate_not_in_past(timezone.now() - timedelta(days=2))
    validate_phone_number('+1 (555) 123-4567')
    with pytest.raises(ValidationError):
        validate_phone_number('12ab')
