"""Attendance, certificates, fee instalments, study materials, sign-in link, merge and the next-batch list."""
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse

from clinic.models import ClinicProfile
from courses import ops, service
from courses.models import (Certificate, Course, CourseBatch, CourseFeePayment, CourseMaterial, CourseRegistration,
                            CourseSession, Student, StudentNote)
from notifications.models import Notification

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture(autouse=True)
def _quiet(settings):
    settings.NOTIFY_SEND_ON_COMMIT = False
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'


@pytest.fixture
def batch(db):
    ClinicProfile.objects.create(name='Clinic', address='x', phone='9876543210')
    c = Course.objects.create(title='Acupressure Basics', short_description='Learn', is_published=True, fees=Decimal('5000'))
    return CourseBatch.objects.create(course=c, name='Batch 1', start_date=date.today() + timedelta(days=5),
                                      end_date=None, is_active=True, is_published=True,
                                      max_participants=10, min_attendance_percent=75)


@pytest.fixture
def admin(client):
    u = User.objects.create_user(username='adm', email='adm@x.com', password='Str0ng!pass9', role='superadmin', is_superuser=True)
    client.force_login(u)
    return u


def two_students(batch):
    a = service.register(batch, name='Asha Raman', phone='9111111111', email='asha@example.com')
    b = service.register(batch, name='Bala Kumar', phone='9222222222', email='bala@example.com')
    CourseBatch.objects.filter(pk=batch.pk).update(start_date=date.today() - timedelta(days=30), end_date=date.today() - timedelta(days=1))
    batch.refresh_from_db()
    return CourseRegistration.objects.get(pk=a.pk), CourseRegistration.objects.get(pk=b.pk)


def run_sessions(batch, a, b):
    days = [CourseSession.objects.create(batch=batch, date=date.today() - timedelta(days=20 - i)) for i in range(4)]
    ticked = {(str(s.pk), str(a.pk)) for s in days}                    # Asha: 4/4
    ticked |= {(str(days[0].pk), str(b.pk))}                           # Bala: 1/4
    ops.save_attendance(batch, ticked)
    return days


def test_attendance_percentages_and_eligibility(batch):
    a, b = two_students(batch)
    run_sessions(batch, a, b)
    assert ops.attendance_percent(a) == 100 and ops.attendance_percent(b) == 25
    assert ops.eligible(a) and not ops.eligible(b)


def test_attendance_page_saves_ticks(client, admin, batch):
    a, b = two_students(batch)
    s = CourseSession.objects.create(batch=batch, date=date.today())
    r = client.post(reverse('batch_attendance', args=[batch.pk]), {'action': 'save', f'm_{s.pk}_{a.pk}': 'on'})
    assert r.status_code == 302
    assert ops.attendance_percent(a) == 100 and ops.attendance_percent(b) == 0
    assert client.get(reverse('batch_attendance', args=[batch.pk])).status_code == 200


def test_certificates_go_only_to_those_who_attended_enough_and_are_emailed_with_a_pdf(batch):
    a, b = two_students(batch)
    run_sessions(batch, a, b)
    issued, emailed = ops.issue_certificates(batch)
    assert (issued, emailed) == (1, 1)
    assert Certificate.objects.get().registration == a and not Certificate.objects.filter(registration=b).exists()
    assert ops.issue_certificates(batch) == (0, 0)                      # never twice
    n = Notification.objects.get(event_type='course_certificate')
    from notifications.service import deliver_notification
    deliver_notification(n.pk)
    sent = mail.outbox[-1]
    assert sent.to == ['asha@example.com'] and sent.attachments[0][0].startswith('certificate-C-')
    assert sent.attachments[0][1][:4] == b'%PDF'


def test_certificate_page_and_verification(client, batch):
    a, b = two_students(batch)
    run_sessions(batch, a, b)
    ops.issue_certificates(batch)
    cert = Certificate.objects.get()
    r = client.get(reverse('course_my_certificate', args=[a.access_token]))
    assert r.status_code == 200 and r.content[:4] == b'%PDF'
    assert client.get(reverse('course_my_certificate', args=[b.access_token])).status_code == 404
    html = client.get(reverse('certificate_verify', args=[cert.code])).content.decode()
    assert 'Genuine certificate' in html and 'Asha' in html and 'Raman' not in html
    assert 'No such certificate' in client.get(reverse('certificate_verify', args=['C-NOPE'])).content.decode()


def test_fee_instalments_and_override(client, admin, batch):
    a, _b = two_students(batch)
    client.post(reverse('fee_payment_add', args=[a.pk]), {'amount': '2000', 'mode': 'upi', 'reference': 'T123'})
    client.post(reverse('fee_payment_add', args=[a.pk]), {'amount': '1500.50', 'mode': 'cash'})
    client.post(reverse('fee_payment_add', args=[a.pk]), {'amount': '-5'})                 # rejected
    client.post(reverse('fee_payment_add', args=[a.pk]), {'amount': 'abc'})                # rejected
    s = ops.fee_summary(CourseRegistration.objects.get(pk=a.pk))
    assert (s['fee'], s['paid'], s['balance']) == (Decimal('5000'), Decimal('3500.50'), Decimal('1499.50'))
    client.post(reverse('fee_override', args=[a.pk]), {'fee': '3500.50'})
    a.refresh_from_db()
    assert ops.fee_summary(a)['balance'] == 0
    page = client.get(reverse('student_detail', args=[a.student_id])).content.decode()
    assert 'settled' in page and 'T123' in page


def test_study_materials_are_private_to_confirmed_students(client, admin, batch):
    a, b = two_students(batch)
    pdf = SimpleUploadedFile('notes.pdf', b'%PDF-1.4 hello', content_type='application/pdf')
    r = client.post(reverse('course_materials', args=[batch.course.pk]), {'title': 'Notes', 'file': pdf, 'is_published': 'on'})
    assert r.status_code == 302
    client.post(reverse('course_materials', args=[batch.course.pk]),
                {'title': 'Slides', 'url': 'https://drive.google.com/x', 'is_published': 'on'})
    fake = SimpleUploadedFile('evil.pdf', b'MZ not a pdf at all', content_type='application/pdf')
    bad = client.post(reverse('course_materials', args=[batch.course.pk]), {'title': 'Bad', 'file': fake})
    assert bad.status_code == 200 and CourseMaterial.objects.count() == 2                   # content must match the name
    both = client.post(reverse('course_materials', args=[batch.course.pk]),
                       {'title': 'Both', 'url': 'https://x.com', 'file': SimpleUploadedFile('a.pdf', b'%PDF-1')})
    assert both.status_code == 200 and CourseMaterial.objects.count() == 2
    m = CourseMaterial.objects.get(title='Notes')
    client.logout()
    assert client.get(reverse('course_my_material', args=[a.access_token, m.pk])).status_code == 200
    assert 'Notes' in client.get(reverse('course_registration_manage', args=[a.access_token])).content.decode()
    CourseRegistration.objects.filter(pk=b.pk).update(status='cancelled')
    assert client.get(reverse('course_my_material', args=[b.access_token, m.pk])).status_code == 404
    assert client.get(reverse('course_my_material', args=['bogus', m.pk])).status_code == 404
    m.is_published = False
    m.save()
    assert client.get(reverse('course_my_material', args=[a.access_token, m.pk])).status_code == 404


def test_signin_link_goes_only_to_the_email_on_file_and_works_once(client, batch):
    a, _b = two_students(batch)
    assert ops.request_signin('9111111111') == 1                       # a phone number: link goes to the stored email
    assert mail.outbox[-1].to == ['asha@example.com']
    assert ops.request_signin('nobody@example.com') == 0 and len(mail.outbox) == 1
    link = [w for w in mail.outbox[-1].body.split() if '/sign-in/' in w][0]
    path = link[link.index('/en/'):] if '/en/' in link else link[link.index('/students'):]
    r = client.get(path)
    assert r.status_code == 302 and r.url.endswith(reverse('student_portal'))
    page = client.get(reverse('student_portal')).content.decode()
    assert 'Acupressure Basics' in page
    assert client.get(path).status_code == 302 and client.get(path).url.endswith(reverse('student_signin'))   # single use
    client.post(reverse('student_signout'))
    assert client.get(reverse('student_portal')).status_code == 302


def test_signin_page_never_reveals_who_is_registered(client, batch):
    two_students(batch)
    known = client.post(reverse('student_signin'), {'identifier': 'asha@example.com'}).content.decode()
    unknown = client.post(reverse('student_signin'), {'identifier': 'ghost@example.com'}).content.decode()
    assert 'sign-in link is on its way' in known and 'sign-in link is on its way' in unknown


def test_merge_moves_everything_to_one_student(client, admin, batch):
    a, _b = two_students(batch)
    other_batch = CourseBatch.objects.create(course=batch.course, name='Batch 2', start_date=date.today() + timedelta(days=30),
                                             is_active=False, is_published=True)
    again = service.register(other_batch, name='Asha R', phone='9111111111', email='asha2@example.com') if False else \
        CourseRegistration.objects.create(batch=other_batch, name='Asha R', phone='9111111111', phone_key='9111111111',
                                          email='asha2@example.com')
    service.link_student(again)
    StudentNote.objects.create(student=again.student, text='called')
    page = client.get(reverse('student_detail', args=[a.student_id])).content.decode()
    assert 'Other students use this phone number' in page and 'Merge into this student' in page
    client.post(reverse('student_merge', args=[a.student_id, again.student_id]))
    again.refresh_from_db()
    assert again.student_id == a.student_id and Student.objects.filter(phone_key='9111111111').count() == 1
    assert StudentNote.objects.get().student_id == a.student_id


def test_ready_for_next_batch_list(client, admin, batch):
    a, b = two_students(batch)
    client.post(reverse('student_note_add', args=[a.student_id]), {'kind': 'next_batch', 'text': 'Ready for the next batch'})
    html = client.get(reverse('student_list'), {'profile': 'next_batch'}).content.decode()
    assert 'Asha Raman' in html and 'Bala Kumar' not in html
    note = StudentNote.objects.get()
    client.post(reverse('student_note_done', args=[a.student_id, note.pk]))
    assert 'Asha Raman' not in client.get(reverse('student_list'), {'profile': 'next_batch'}).content.decode()


def test_batch_attendance_needs_permission(client, batch):
    client.force_login(User.objects.create_user(username='x', email='x@x.com', password='Str0ng!pass9', role='doctor'))
    assert client.get(reverse('batch_attendance', args=[batch.pk])).status_code in (302, 403)
    assert client.post(reverse('batch_issue_certificates', args=[batch.pk])).status_code in (302, 403)
