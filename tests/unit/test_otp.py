from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import OTPToken


@pytest.fixture
def user(patient_user):
    return patient_user


def test_generate_then_verify(user):
    token, code, created = OTPToken.generate_otp_token(user)
    assert created and len(code) == 6 and token.otp_value == ''      # code is never persisted
    ok, used, err = OTPToken.verify_otp(user, code)
    assert ok and err is None and used.is_used


def test_wrong_code_counts_down_then_locks(user):
    OTPToken.generate_otp_token(user)
    for left in (4, 3, 2, 1):
        ok, _, err = OTPToken.verify_otp(user, '000000')
        assert not ok and str(left) in str(err)
    ok, _, err = OTPToken.verify_otp(user, '000000')
    assert not ok and 'Too many failed attempts' in str(err)
    ok, _, err = OTPToken.verify_otp(user, '000000')
    assert not ok and 'Too many failed attempts' in str(err)


def test_code_is_single_use(user):
    _, code, _ = OTPToken.generate_otp_token(user)
    assert OTPToken.verify_otp(user, code)[0]
    assert not OTPToken.verify_otp(user, code)[0]


def test_new_request_invalidates_previous(user):
    _, first, _ = OTPToken.generate_otp_token(user)
    _, second, _ = OTPToken.generate_otp_token(user)
    if first != second:
        assert not OTPToken.verify_otp(user, first)[0]


def test_expired_code_rejected(user):
    token, code, _ = OTPToken.generate_otp_token(user)
    OTPToken.objects.filter(pk=token.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    ok, _, err = OTPToken.verify_otp(user, code)
    assert not ok and 'No valid OTP' in str(err)


def test_hourly_request_limit(user):
    for _ in range(3):
        OTPToken.generate_otp_token(user)
    with pytest.raises(PermissionError):
        OTPToken.generate_otp_token(user)


def test_cleanup_removes_only_expired(user):
    token, _, _ = OTPToken.generate_otp_token(user)
    OTPToken.objects.filter(pk=token.pk).update(expires_at=timezone.now() - timedelta(days=2))
    OTPToken.cleanup_expired_tokens()
    assert not OTPToken.objects.filter(pk=token.pk).exists()


def test_new_request_does_not_reset_failed_attempts_via_same_row(user):
    first, _, _ = OTPToken.generate_otp_token(user)
    OTPToken.verify_otp(user, '000000')
    second, _, _ = OTPToken.generate_otp_token(user)
    assert second.pk != first.pk and OTPToken.objects.filter(user=user).count() == 2
