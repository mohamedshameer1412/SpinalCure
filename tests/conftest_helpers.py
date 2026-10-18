from patients.models import Patient


def make_patient(**kw):
    data = dict(name='Kavitha Balakrishnan', phone='9876543210', address='Chennai', chief_complaint='Back pain')
    data.update(kw)
    return Patient.objects.create(**data)


def make_practitioner(**kw):
    from clinic.models import Practitioner
    data = dict(name='Dr. Arun', specialization='Acupuncture', experience_years=5, is_active=True, email='doctor@test.com')
    data.update(kw)
    return Practitioner.objects.create(**data)


def next_weekday(weekday, weeks_ahead=1):
    """A date `weeks_ahead` weeks from now on the given weekday (0=Monday); always in the future."""
    from datetime import timedelta
    from django.utils import timezone
    today = timezone.localdate()
    return today + timedelta(days=(weekday - today.weekday()) % 7 + 7 * weeks_ahead)
