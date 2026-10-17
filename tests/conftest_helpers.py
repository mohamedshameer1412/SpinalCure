from patients.models import Patient


def make_patient(**kw):
    data = dict(name='Kavitha Balakrishnan', phone='9876543210', address='Chennai', chief_complaint='Back pain')
    data.update(kw)
    return Patient.objects.create(**data)
