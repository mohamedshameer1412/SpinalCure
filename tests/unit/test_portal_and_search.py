"""Patient-portal OTP login, blind index, encrypted search and key handling."""
import re

import pytest
from django.core import mail
from django.core.cache import cache
from django.db import connection
from django.test import Client

from patients.models import Patient
from patients.search import matching_patient_ids
from spinalcure.blind_index import phone_index


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.fixture
def pat():
    return Patient.objects.create(name='Asha Raman', phone='+91 98765 43210', email='asha@example.com',
                                  chief_complaint='Lower back pain')


def _code_from_mail():
    return re.search(r'code is (\d{6})', mail.outbox[-1].body).group(1)


def test_phone_is_not_searchable_in_sql_but_blind_index_works(pat):
    with connection.cursor() as cur:
        cur.execute('SELECT phone FROM patients_patient')
        raw = cur.fetchone()[0]
    assert '98765' not in raw  # stored encrypted
    assert Patient.objects.filter(phone_index=phone_index('9876543210')).get() == pat
    assert Patient.objects.filter(phone_index=phone_index('+91-98765-43210')).exists()
    assert not Patient.objects.filter(phone_index=phone_index('9999999999')).exists()


def test_search_matches_decrypted_name_phone_and_complaint(pat):
    assert matching_patient_ids('raman') == [pat.pk]
    assert matching_patient_ids('98765 43210') == [pat.pk]
    assert matching_patient_ids('back pain') == [pat.pk]
    assert matching_patient_ids('zzz') == []


def test_portal_login_happy_path(pat):
    c = Client()
    assert c.post('/en/patients/portal/login/', {'phone': '9876543210'}).status_code == 302
    assert len(mail.outbox) == 1
    code = _code_from_mail()
    resp = c.post('/en/patients/portal/verify/', {'otp': code})
    assert resp.status_code == 302 and resp.url.endswith('/portal/dashboard/')
    assert c.get('/en/patients/portal/dashboard/').status_code == 200


def test_hardcoded_legacy_code_is_rejected(pat):
    c = Client()
    c.post('/en/patients/portal/login/', {'phone': '9876543210'})
    real = _code_from_mail()
    guess = '123456' if real != '123456' else '654321'
    c.post('/en/patients/portal/verify/', {'otp': guess})
    assert c.get('/en/patients/portal/dashboard/').status_code == 302  # still logged out


def test_unknown_phone_looks_identical_and_sends_nothing(pat):
    c1, c2 = Client(), Client()
    r1 = c1.post('/en/patients/portal/login/', {'phone': '9876543210'})
    r2 = c2.post('/en/patients/portal/login/', {'phone': '9000000000'})
    assert (r1.status_code, r1.url) == (r2.status_code, r2.url)
    assert len(mail.outbox) == 1


def test_wrong_code_locks_challenge_after_five_attempts(pat):
    c = Client()
    c.post('/en/patients/portal/login/', {'phone': '9876543210'})
    code = _code_from_mail()
    wrong = '000000' if code != '000000' else '111111'
    for _ in range(6):
        c.post('/en/patients/portal/verify/', {'otp': wrong})
    c.post('/en/patients/portal/verify/', {'otp': code})
    assert c.get('/en/patients/portal/dashboard/').status_code == 302


def test_per_phone_request_throttle(pat):
    codes = [Client().post('/en/patients/portal/login/', {'phone': '9876543210'}).status_code for _ in range(5)]
    assert codes[:3] == [302, 302, 302] and 429 in codes[3:]
    assert len(mail.outbox) == 3


def test_login_page_has_no_demo_code_hint(pat):
    c = Client()
    c.post('/en/patients/portal/login/', {'phone': '9876543210'})
    assert b'123456' not in c.get('/en/patients/portal/verify/').content
