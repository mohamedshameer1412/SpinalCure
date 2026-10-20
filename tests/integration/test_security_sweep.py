"""Security re-sweep regressions: is_staff grants nothing, audit revert is super-admin only, no open redirects,
the map embed cannot carry script, and uploaded "images" must really be images with a safe extension."""
import io
from datetime import date, time

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from PIL import Image

from clinic.models import AuditLog, ClinicProfile, Practitioner

pytestmark = [pytest.mark.django_db]
User = get_user_model()


def login(role, **extra):
    u = User.objects.create_user(username=f'u-{role}-{len(extra)}', email=f'{role}{len(extra)}@x.com', password='x-Str0ng-pass!',
                                 role=role, **extra)
    c = Client()
    c.force_login(u)
    return c


def test_is_staff_flag_does_not_open_website_management():
    c = login('receptionist', is_staff=True)
    assert c.get(reverse('admin_testimonials')).status_code == 302
    assert c.get(reverse('admin_clinic_setup')).status_code == 302


def test_owner_can_manage_website_per_capability_matrix():
    assert login('owner').get(reverse('admin_testimonials')).status_code == 200


def test_only_super_admin_can_revert_audit_log():
    log = AuditLog.objects.create(action='update', model_name='Practitioner', object_repr='x', object_id='1')
    r = login('owner').post(reverse('admin_revert_log', args=[log.pk]))
    assert r.status_code == 403


@override_settings(ALLOWED_HOSTS=['testserver'])
def test_event_status_next_cannot_redirect_off_site():
    from events.models import Event
    c = login('owner')
    clinic = ClinicProfile.objects.create(name='C', address='A', phone='+914400000000')
    e = Event.objects.create(clinic=clinic, title='T', date=date(2030, 1, 1), start_time=time(9), end_time=time(10))
    r = c.post(reverse('event_status', args=[e.pk]), {'status': 'draft', 'next': 'https://evil.example/phish'})
    assert r.status_code == 302 and 'evil.example' not in r['Location']
    r = c.post(reverse('event_status', args=[e.pk]), {'status': 'draft', 'next': '/en/events/'})
    assert r['Location'] == '/en/events/'


@pytest.mark.parametrize('pasted, ok', [
    ('<iframe src="https://www.google.com/maps/embed?pb=!1m18" width="600"></iframe>', True),
    ('https://www.google.com/maps/embed?pb=!1m18', True),
    ('<iframe src="https://evil.example/maps/embed"></iframe>', False),
    ('<script>alert(1)</script>', False),
    ('<iframe src="javascript:alert(1)"></iframe>', False)])
def test_map_embed_only_renders_google_maps(pasted, ok):
    clinic = ClinicProfile.objects.create(name='C', address='A', phone='+914400000000', map_iframe_url=pasted)
    assert bool(clinic.map_embed_src) is ok
    html = Client().get('/en/').content.decode()
    assert '<script>alert(1)' not in html and 'javascript:alert' not in html


def test_html_disguised_as_image_is_rejected_and_real_image_gets_safe_name(tmp_path):
    from spinalcure.uploads import UploadRejected, checked_image
    with pytest.raises(UploadRejected):
        checked_image(SimpleUploadedFile('cover.png', b'<html><script>alert(1)</script>', content_type='image/png'))
    buf = io.BytesIO()
    Image.new('RGB', (10, 10)).save(buf, 'PNG')
    polyglot = SimpleUploadedFile('cover.html', buf.getvalue() + b'<script>alert(1)</script>', content_type='text/html')
    assert checked_image(polyglot).name.endswith('.png')


def test_bad_practitioner_photo_shows_message_not_500(tmp_path):
    with override_settings(MEDIA_ROOT=tmp_path):
        c = login('owner')
        r = c.post(reverse('admin_practitioner_create'), {'name': 'Dr X', 'photo': SimpleUploadedFile('a.jpg', b'nope')}, follow=True)
    assert r.status_code == 200 and not Practitioner.objects.filter(name='Dr X', photo__gt='').exists()
