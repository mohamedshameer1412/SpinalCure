"""Field encryption, key rotation safety and encrypted-field search."""
import pytest
from cryptography.fernet import Fernet
from django.db import connection

from patients.models import Patient, AcupunctureDiagnosis

pytestmark = pytest.mark.django_db


def _raw(table, column, pk):
    with connection.cursor() as c:
        c.execute(f'SELECT {column} FROM {table} WHERE id = %s', [pk.hex])
        return c.fetchone()[0]


def make_patient(**kw):
    data = dict(name='Kavitha Balakrishnan', phone='98765 43210', address='Anna Nagar, Chennai',
                chief_complaint='Lower back pain')
    data.update(kw)
    return Patient.objects.create(**data)


def test_pii_is_ciphertext_at_rest_and_round_trips():
    p = make_patient(name='முருகன் செல்வம்')
    assert _raw('patients_patient', 'name', p.pk).startswith('gAAAAA')
    assert 'Chennai' not in _raw('patients_patient', 'address', p.pk)
    assert Patient.objects.get(pk=p.pk).name == 'முருகன் செல்வம்'


def test_json_diagnosis_round_trips_encrypted():
    p = make_patient()
    d = AcupunctureDiagnosis.objects.create(patient=p, diagnosis_data={'tongue': 'pale', 'pulse': ['slow']})
    assert _raw('patients_acupuncturediagnosis', 'diagnosis_data', d.pk).startswith('gAAAAA')
    d = AcupunctureDiagnosis.objects.get(pk=d.pk)
    assert d.diagnosis_data == {'tongue': 'pale', 'pulse': ['slow']}
    d.save()  # re-save must not double-encrypt
    assert AcupunctureDiagnosis.objects.get(pk=d.pk).diagnosis_data['tongue'] == 'pale'


def test_wrong_key_fails_loudly(settings):
    p = make_patient()
    settings.FERNET_KEYS = [Fernet.generate_key().decode()]
    with pytest.raises(RuntimeError):
        Patient.objects.get(pk=p.pk)


def test_rotation_keeps_data_readable(settings):
    from django.core.management import call_command
    p = make_patient()
    new = Fernet.generate_key().decode()
    settings.FERNET_KEYS = [new, *settings.FERNET_KEYS]
    call_command('rotate_encryption_key', stdout=open('/dev/null', 'w'))
    settings.FERNET_KEYS = [new]
    p = Patient.objects.get(pk=p.pk)
    assert p.name == 'Kavitha Balakrishnan'
    assert Patient.by_phone('9876543210') == p


def test_search_by_name_phone_and_id():
    p = make_patient(patient_id_str='SC-0042')
    make_patient(name='Other Person', phone='9000000001')
    qs = Patient.objects.all()
    assert list(Patient.search(qs, 'kavitha')) == [p]
    assert list(Patient.search(qs, '+91 98765-43210')) == [p]
    assert list(Patient.search(qs, 'SC-0042')) == [p]
    assert list(Patient.search(qs, 'nobody')) == []
    assert Patient.by_phone('(987) 654-3210') == p
