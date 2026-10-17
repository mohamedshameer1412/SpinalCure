"""Staff password-reset OTP: hashed storage, verification, brute-force lockout."""
import pytest
from django.utils import timezone

from accounts.models import OTPToken


@pytest.fixture
def user(make_user):
    return make_user('doctor')


def test_code_is_stored_hashed_and_verifies(user):
    token, code, _ = OTPToken.generate_otp_token(user)
    assert len(code) == 6 and code.isdigit()
    token.refresh_from_db()
    assert code not in token.otp_value
    ok, _t, err = OTPToken.verify_otp(user, code)
    assert ok and err is None
    assert OTPToken.verify_otp(user, code)[0] is False  # single use


def test_five_wrong_codes_lock_the_token(user):
    _t, code, _ = OTPToken.generate_otp_token(user)
    wrong = '000000' if code != '000000' else '111111'
    for _ in range(5):
        assert OTPToken.verify_otp(user, wrong)[0] is False
    assert OTPToken.verify_otp(user, code)[0] is False


def test_expired_code_is_rejected(user):
    token, code, _ = OTPToken.generate_otp_token(user)
    OTPToken.objects.filter(pk=token.pk).update(expires_at=timezone.now())
    assert OTPToken.verify_otp(user, code)[0] is False


def test_new_request_invalidates_previous_code(user):
    _t, first, _ = OTPToken.generate_otp_token(user)
    _t, second, _ = OTPToken.generate_otp_token(user)
    if first != second:
        assert OTPToken.verify_otp(user, first)[0] is False
    assert OTPToken.verify_otp(user, second)[0] is True


def test_hourly_request_limit(user):
    for _ in range(3):
        OTPToken.generate_otp_token(user)
    with pytest.raises(PermissionError):
        OTPToken.generate_otp_token(user)
