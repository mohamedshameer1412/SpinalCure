"""The public site's opening hours follow Availability; address links open the map; every social link shows in header and footer."""
from datetime import time

import pytest
from django.test import Client

from appointments.models import DoctorAvailability
from clinic import hours
from clinic.models import ClinicProfile, Practitioner

pytestmark = pytest.mark.django_db


@pytest.fixture
def clinic():
    return ClinicProfile.objects.create(
        name='Spinal Cure', address='No: 194/4, JN Salai, Arumbakkam, Chennai 600106', phone='+918148038363',
        working_hours='Old text: 9 to 5', facebook='https://facebook.com/spinalcure', twitter='https://x.com/spinalcure',
        instagram='https://instagram.com/spinalcure', youtube='https://youtube.com/@spinalcure')


@pytest.fixture
def doctor(db):
    return Practitioner.objects.create(name='Dr Rao', is_active=True)


def shift(doc, day, a, b):
    DoctorAvailability.objects.create(practitioner=doc, day_of_week=day, start_time=a, end_time=b, is_available=True)


def test_hours_text_follows_the_weekly_availability(clinic, doctor):
    assert hours.opening_hours(clinic) == 'Old text: 9 to 5'                    # nothing set yet: the old text is the fallback
    for d in (0, 1, 2, 3, 5):
        shift(doctor, d, time(10, 30), time(13, 30))
        shift(doctor, d, time(17, 30), time(20, 30))
    shift(doctor, 4, time(17, 30), time(20, 30))                                # Friday: evening only
    shift(doctor, 6, time(6, 0), time(7, 45))
    text = hours.opening_hours(clinic)
    assert text.splitlines() == ['Mon–Thu, Sat: 10:30 a.m. – 1:30 p.m., 5:30 p.m. – 8:30 p.m.',
                                 'Fri: 5:30 p.m. – 8:30 p.m.', 'Sun: 6:00 a.m. – 7:45 a.m.']
    html = Client().get('/en/').content.decode()
    assert 'Fri: 5:30 p.m. – 8:30 p.m.' in html and 'Old text' not in html
    shift(doctor, 6, time(9, 0), time(10, 0))                                   # a change is live on the next request
    assert 'Sun: 6:00 a.m. – 7:45 a.m., 9:00 a.m. – 10:00 a.m.' in Client().get('/en/').content.decode()


def test_days_without_any_shift_read_closed(clinic, doctor):
    for d in range(6):
        shift(doctor, d, time(10, 30), time(13, 30))
    assert hours.weekly_hours().splitlines() == ['Mon–Sat: 10:30 a.m. – 1:30 p.m.', 'Sun: Closed']


def test_address_links_to_maps_and_social_icons_are_everywhere(clinic):
    html = Client().get('/en/').content.decode()
    assert html.count('google.com/maps/search/?api=1&amp;query=No%3A%20194') >= 3          # header, home section, footer
    for who in ('facebook', 'x.com', 'instagram', 'youtube'):
        assert html.count(f'https://{who if "." in who else who + ".com"}/') >= 1
    header = html.split('</header>')[0]
    assert 'bi-facebook' in header and 'bi-twitter-x' in header and 'bi-instagram' in header and 'bi-youtube' in header
    clinic.map_link = 'https://maps.app.goo.gl/abc123'
    clinic.save()
    html = Client().get('/en/').content.decode()
    assert html.count('href="https://maps.app.goo.gl/abc123"') >= 3 and 'maps/search' not in html
