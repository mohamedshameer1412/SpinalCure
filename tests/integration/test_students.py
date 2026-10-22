"""Student platform: one record per person, details collected after confirmation, ID card, feedback, follow-ups."""
import io
import json
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse
from PIL import Image

from clinic.models import ClinicProfile
from courses import service
from courses.models import Course, CourseBatch, CourseRegistration, Student, StudentNote
from notifications.models import Notification

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture(autouse=True)
def _quiet(settings):
    settings.NOTIFY_SEND_ON_COMMIT = False


@pytest.fixture
def batch(db):
    ClinicProfile.objects.create(name='Clinic', address='x', phone='9876543210')
    c = Course.objects.create(title='Acupressure Basics', short_description='Learn', is_published=True)
    return CourseBatch.objects.create(course=c, name='Batch 1', start_date=date.today() + timedelta(days=14),
                                      is_active=True, is_published=True, max_participants=5)


def photo():
    buf = io.BytesIO()
    Image.new('RGB', (200, 240), (120, 160, 120)).save(buf, 'JPEG')
    return SimpleUploadedFile('me.jpg', buf.getvalue(), content_type='image/jpeg')


def details(**over):
    data = {'action': 'profile', 'photo': photo(), 'email': 'asha@example.com', 'designation': 'Physiotherapist',
            'address': '12 Main Road, Chennai', 'organisation': '', 'gender': 'F', 'blood_group': '', 'date_of_birth': '',
            'emergency_contact_name': '', 'emergency_contact_phone': ''}
    data.update(over)
    return data


def test_registering_creates_one_student_per_person_and_asks_for_details(batch):
    reg = service.register(batch, name='Asha Raman', phone='9876543210', email='asha@example.com')
    assert reg.student and reg.student.student_code and not reg.student.profile_complete
    n = Notification.objects.get(event_type='course_profile_request')
    assert n.email == 'asha@example.com' and reg.access_token in n.url
    other = CourseBatch.objects.create(course=batch.course, name='Batch 2', start_date=date.today() + timedelta(days=60),
                                       is_active=False, is_published=True)
    again = CourseRegistration.objects.create(batch=other, name='Asha R', phone='98765 43210', phone_key='9876543210')
    assert service.link_student(again) == reg.student and Student.objects.count() == 1


def test_student_completes_details_and_gets_a_card(client, batch):
    reg = service.register(batch, name='Asha Raman', phone='9876543210', email='')
    assert not Notification.objects.filter(event_type='course_profile_request').exists()   # no email yet: staff share the link
    url = reverse('course_registration_manage', args=[reg.access_token])
    r = client.post(url, details(email=''))                                 # email is required when none was given
    assert r.status_code == 200 and not Student.objects.get().profile_complete
    r = client.post(url, details())
    assert r.status_code == 302
    st = Student.objects.get()
    assert st.profile_complete and st.email == 'asha@example.com' and st.designation == 'Physiotherapist'
    assert Notification.objects.filter(event_type='course_card_ready', email='asha@example.com').count() == 1
    png = client.get(reverse('course_student_card', args=[reg.access_token, 'front']))
    assert png.status_code == 200 and png['Content-Type'] == 'image/png' and png.content[:4] == b'\x89PNG'
    assert client.get(reverse('course_student_card_pdf', args=[reg.access_token])).content[:4] == b'%PDF'
    page = client.get(url).content.decode()
    assert 'Your student ID card' in page


def test_card_is_not_served_before_details_are_complete(client, batch):
    reg = service.register(batch, name='Asha Raman', phone='9876543210', email='a@example.com')
    assert client.get(reverse('course_student_card', args=[reg.access_token, 'front'])).status_code == 404
    assert client.get(reverse('course_student_card', args=['nope', 'front'])).status_code == 404


def test_public_verify_shows_first_name_only(client, batch):
    reg = service.register(batch, name='Asha Quillfeather', phone='9111111111', email='a@example.com')
    client.post(reverse('course_registration_manage', args=[reg.access_token]), details())
    st = Student.objects.get()
    html = client.get(reverse('student_verify', args=[st.student_code])).content.decode()
    assert 'Valid student ID' in html and 'Asha' in html and 'Quillfeather' not in html and '9111111111' not in html
    assert 'No such student ID' in client.get(reverse('student_verify', args=['0000-AAA'])).content.decode()


def test_staff_pages_need_permission_and_notes_work(client, batch):
    reg = service.register(batch, name='Asha Raman', phone='9876543210', email='a@example.com')
    st = reg.student
    client.force_login(User.objects.create_user(username='r', email='r@x.com', password='Str0ng!pass9', role='doctor'))
    assert client.get(reverse('student_list')).status_code in (302, 403)
    client.force_login(User.objects.create_user(username='o', email='o@x.com', password='Str0ng!pass9', role='superadmin',
                                                is_superuser=True))
    assert client.get(reverse('student_list')).status_code == 200
    assert 'Asha Raman' in client.get(reverse('student_list'), {'q': 'asha'}).content.decode()
    assert client.get(reverse('student_detail', args=[st.pk])).status_code == 200
    client.post(reverse('student_note_add', args=[st.pk]), {'kind': 'call', 'text': 'Called, will pay Friday',
                                                              'follow_up_on': (date.today() - timedelta(days=1)).isoformat()})
    note = StudentNote.objects.get()
    assert note.kind == 'call' and note.follow_up_on
    assert 'Asha Raman' in client.get(reverse('student_list'), {'profile': 'follow_up'}).content.decode()
    client.post(reverse('student_note_done', args=[st.pk, note.pk]))
    note.refresh_from_db()
    assert note.done


def test_feedback_request_opens_the_form_and_emails_each_student_once(batch):
    r1 = service.register(batch, name='A One', phone='9000000001', email='a1@example.com')
    service.register(batch, name='B Two', phone='9000000002', email='')
    batch.end_date = date.today() - timedelta(days=1)
    batch.save()
    assert service.request_feedback(batch) == 1
    batch.refresh_from_db()
    assert batch.feedback_enabled
    assert Notification.objects.filter(event_type='course_feedback_request').count() == 1
    assert service.request_feedback(batch) == 0                           # never twice
    r1.refresh_from_db()
    assert r1.completed_at


def test_cron_sends_start_reminders_profile_nudges_and_feedback(batch):
    reg = service.register(batch, name='Asha Raman', phone='9876543210', email='a@example.com')
    batch.start_date = date.today() + timedelta(days=1)
    batch.save()
    CourseRegistration.objects.filter(pk=reg.pk).update(registered_at=reg.registered_at - timedelta(days=3))
    call_command('send_reminders')
    assert Notification.objects.filter(event_type='course_batch_reminder').count() == 1
    assert Notification.objects.filter(event_type='course_profile_request').count() == 2     # request + one reminder
    call_command('send_reminders')
    assert Notification.objects.filter(event_type='course_batch_reminder').count() == 1      # idempotent
    batch.start_date, batch.end_date = date.today() - timedelta(days=10), date.today() - timedelta(days=1)
    batch.save()
    call_command('send_reminders')
    assert Notification.objects.filter(event_type='course_feedback_request').count() == 1
