"""Private feedback, review requests, FAQs, session packages, story card tagging and the Shorts banner crop."""
import io
import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from appointments.models import BookingSettings
from clinic import stories
from clinic.models import FAQ, ClinicTestimonial, ProblemCategory, TestimonialVideo
from notifications.models import Notification
from patients.models import Patient, Session, SessionPackage, TreatmentPlan
from tests.integration.test_stories import post_review

User = get_user_model()


def staff(role):
    return User.objects.create_user(username=f'e-{role}', email=f'e-{role}@x.com', password='x-Str0ng-pass!', role=role)


# ── private feedback ─────────────────────────────────────────────────────────────────────────────────────

def test_private_feedback_needs_no_consent_and_can_never_be_published(clinic_profile, superuser):
    r = post_review(kind='feedback', consent=False, review='The waiting room was too warm in the evening.')
    assert r.status_code == 200 and 'withdraw_url' not in r.json()
    t = ClinicTestimonial.objects.get()
    assert (t.consent_to_publish, t.is_published, t.moderation_status) == (False, False, 'pending')
    assert stories.moderate(t, 'publish', superuser) != ''          # refused: the author never agreed
    t.refresh_from_db()
    assert not t.is_published


def test_public_review_still_requires_consent(clinic_profile):
    assert post_review(kind='review', consent=False).status_code == 400


# ── review requests ──────────────────────────────────────────────────────────────────────────────────────

def sessions(patient, n, last):
    for i in range(n):
        Session.objects.create(patient=patient, session_number=i + 1, session_date=last - timedelta(days=n - 1 - i),
                               acupoints_used='GB30, BL23')


def test_review_request_sent_once_after_n_sessions(clinic_profile):
    p = Patient.objects.create(name='Asha', phone='9000000101', email='asha@example.com', gender='F')
    sessions(p, 3, timezone.localdate() - timedelta(days=1))
    early = Patient.objects.create(name='Bala', phone='9000000102', email='bala@example.com', gender='M')
    sessions(early, 2, timezone.localdate() - timedelta(days=1))
    old = Patient.objects.create(name='Chitra', phone='9000000103', email='c@example.com', gender='F')
    sessions(old, 5, timezone.localdate() - timedelta(days=90))
    call_command('send_reminders')
    call_command('send_reminders')
    sent = Notification.objects.filter(event_type='review_request')
    assert [n.patient_id for n in sent] == [p.pk]                    # once; not too early, not long-gone patients
    assert sent.get().url.endswith(reverse('clinic_review'))


def test_review_request_can_be_switched_off(clinic_profile):
    cfg = BookingSettings.get()
    cfg.review_request_after_sessions = 0
    cfg.save()
    p = Patient.objects.create(name='Asha', phone='9000000101', email='asha@example.com', gender='F')
    sessions(p, 6, timezone.localdate() - timedelta(days=1))
    call_command('send_reminders')
    assert not Notification.objects.filter(event_type='review_request').exists()


# ── FAQ ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_faq_page_shows_only_published_answers_with_matching_structured_data(clinic_profile):
    FAQ.objects.create(question='Does acupuncture hurt?', answer='A light prick.', is_published=True, reviewed_by='Dr. B')
    FAQ.objects.create(question='Draft question?', answer='Not checked yet.', is_published=False)
    html = Client().get(reverse('clinic_faq')).content.decode()
    assert 'Does acupuncture hurt?' in html and 'Draft question?' not in html
    ld = [json.loads(b.split('>', 1)[1]) for b in html.split('<script type="application/ld+json"')[1:]
          for b in [b.split('</script>')[0]]]
    faq = next(d for d in ld if d.get('@type') == 'FAQPage')
    assert [q['name'] for q in faq['mainEntity']] == ['Does acupuncture hurt?']


def test_publishing_an_faq_requires_who_checked_it(client, superuser):
    client.force_login(superuser)
    r = client.post(reverse('admin_faqs'), {'question': 'Q?', 'answer': 'A.', 'order': 0, 'is_published': 'on'})
    assert r.status_code == 200 and not FAQ.objects.exists()
    client.post(reverse('admin_faqs'), {'question': 'Q?', 'answer': 'A.', 'order': 0, 'is_published': 'on',
                                        'reviewed_by': 'Dr. R. Basheer Basha'})
    assert FAQ.objects.get().is_published


@pytest.mark.parametrize('role, ok', [('owner', True), ('receptionist', False), ('staff', False)])
def test_faq_admin_is_website_management_only(client, role, ok):
    client.force_login(staff(role))
    assert (client.get(reverse('admin_faqs')).status_code == 200) is ok


# ── session packages ─────────────────────────────────────────────────────────────────────────────────────

def test_plan_from_package_copies_sittings_price_and_validity(client, superuser):
    pkg = SessionPackage.objects.create(name='10 sittings', sittings=10, price=Decimal('8000'), validity_days=90)
    p = Patient.objects.create(name='Devi', phone='9000000111', gender='F')
    client.force_login(superuser)
    client.post(reverse('treatment-plan-create', args=[p.pk]), {'name': 'Back pain', 'total_sittings': '', 'package': str(pkg.pk),
                                                                'is_active': 'on'})
    plan = TreatmentPlan.objects.get()
    assert (plan.total_sittings, plan.package_price) == (10, Decimal('8000'))
    assert plan.valid_until == timezone.localdate() + timedelta(days=90)
    assert plan.package_due == Decimal('8000') and plan.remaining_sittings == 10
    plan.valid_until = date.today() - timedelta(days=1)
    assert plan.is_expired


@pytest.mark.parametrize('role, ok', [('owner', True), ('clinicadmin', True), ('receptionist', False), ('doctor', False)])
def test_package_catalogue_is_management_only(client, role, ok):
    client.force_login(staff(role))
    client.post(reverse('session_packages'), {'name': 'Pack', 'sittings': 5, 'price': '4000', 'order': 0, 'is_active': 'on'})
    assert SessionPackage.objects.exists() is ok


# ── story cards ──────────────────────────────────────────────────────────────────────────────────────────

def test_quick_tag_sets_the_problem_and_cards_hide_faces(client, superuser, clinic_profile):
    prob = ProblemCategory.objects.create(name='Sciatica')
    v = TestimonialVideo.objects.create(title='Story', url='https://www.youtube.com/shorts/abcdefghijk',
                                        consent_status='obtained', is_published=True)
    client.force_login(superuser)
    client.post(reverse('admin_video_problem', args=[v.pk]), {'problem': str(prob.pk)})
    v.refresh_from_db()
    assert v.problem == prob
    html = Client().get(reverse('public_testimonials')).content.decode()
    assert 'Sciatica' in html and 'i.ytimg.com/vi/abcdefghijk/hqdefault' not in html.split('application/ld+json')[0]


def test_neighbouring_cards_never_share_a_design():
    vids = stories.with_slots(TestimonialVideo(title=str(i)) for i in range(12))
    for a, b in zip(vids, vids[1:]):
        assert (a.card_variant, a.hue) != (b.card_variant, b.hue)
    for a, b in zip(vids, vids[4:]):                                 # the card below in a 4-column grid
        assert a.card_variant != b.card_variant


def test_banner_is_detected_and_cut_from_shorts_frames():
    img = Image.new('RGB', (1080, 1920), (200, 160, 140))            # "face" area
    img.paste((10, 10, 160), (0, 1600, 1080, 1920))                   # clinic title banner at the bottom
    assert 0.8 < stories.banner_top(img) < 0.86
    buf = io.BytesIO()
    img.save(buf, 'JPEG')
    out = Image.open(io.BytesIO(stories._trim_bars(buf.getvalue())))
    assert out.height < 1600 and out.width == 1080
    plain = Image.new('RGB', (1080, 1920), (60, 80, 160))             # a blue sari, not the banner
    assert stories.banner_top(plain) is None


# ── staff reviews reach the public stories page ──────────────────────────────────────────────────────

def test_publishing_a_staff_review_shows_it_on_patient_stories(client, superuser, clinic_profile):
    from patients.models import PatientReview
    p = Patient.objects.create(name='Meena Raghavan', phone='9000000121', gender='F')
    r = PatientReview.objects.create(patient=p, rating=5, review_text='Neck pain is gone after six sittings.')
    client.force_login(superuser)
    client.post(reverse('review-toggle', args=[r.pk]))
    story = ClinicTestimonial.objects.get(pk=PatientReview.objects.get(pk=r.pk).public_testimonial_id)
    assert story.is_published and story.patient_name == 'Meena'                  # first name only
    assert 'Neck pain is gone' in Client().get(reverse('public_testimonials')).content.decode()
    client.post(reverse('review-toggle', args=[r.pk]))                            # unpublish hides it again
    story.refresh_from_db()
    assert not story.is_published
    assert client.get(reverse('review-toggle', args=[r.pk])).status_code == 405   # no state change by GET


def test_receptionist_cannot_publish_reviews(client, clinic_profile):
    from patients.models import PatientReview
    p = Patient.objects.create(name='Meena', phone='9000000122', gender='F')
    r = PatientReview.objects.create(patient=p, rating=5, review_text='Good.')
    client.force_login(staff('receptionist'))
    client.post(reverse('review-toggle', args=[r.pk]))
    assert not PatientReview.objects.get(pk=r.pk).is_published


# ── full price / discount and non-refundable terms ───────────────────────────────────────────────────

def test_discount_is_shown_struck_out_and_validated(clinic_profile):
    from django.core.exceptions import ValidationError
    from courses.models import Course
    c = Course.objects.create(title='Acupuncture', description='d', fees=Decimal('45000'), original_fees=Decimal('75000'),
                              is_published=True)
    assert c.has_discount and c.discount_percent == 40
    html = Client().get(reverse('course_detail', args=[c.pk])).content.decode()
    assert '<del' in html and '40% off' in html and reverse('clinic_terms') in html
    c.original_fees = Decimal('40000')
    with pytest.raises(ValidationError):
        c.full_clean()


def test_paid_registration_requires_accepting_the_terms(clinic_profile):
    from courses.models import Course, CourseBatch
    c = Course.objects.create(title='Paid', description='d', fees=Decimal('1000'), is_published=True)
    CourseBatch.objects.create(course=c, name='B1', start_date=date.today() + timedelta(days=7), is_active=True)
    url = reverse('course_register_ajax', args=[c.pk])
    body = {'name': 'Ravi Kumar', 'phone': '9000000131', 'email': ''}
    assert Client().post(url, json.dumps(body), content_type='application/json').json()['code'] == 'terms'
    ok = Client().post(url, json.dumps({**body, 'accept_terms': True}), content_type='application/json')
    assert ok.json()['status'] == 'success'


# ── gallery ──────────────────────────────────────────────────────────────────────────────────────────

def test_gallery_shows_published_items_with_the_featured_spotlight(clinic_profile):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from clinic.models import GalleryItem
    buf = io.BytesIO(); Image.new('RGB', (40, 40), 'white').save(buf, 'JPEG')
    img = lambda: SimpleUploadedFile('p.jpg', buf.getvalue(), content_type='image/jpeg')
    GalleryItem.objects.create(title='Our clinic', image=img())
    GalleryItem.objects.create(title='Special visit', image=img(), is_featured=True, featured_label='Featured patient')
    GalleryItem.objects.create(title='Hidden one', image=img(), is_published=False)
    html = Client().get(reverse('public_gallery')).content.decode()
    assert 'Featured patient' in html and 'Special visit' in html and 'Our clinic' in html and 'Hidden one' not in html


@pytest.mark.parametrize('role, ok', [('owner', True), ('receptionist', False)])
def test_gallery_manager_is_website_management_only(client, role, ok):
    client.force_login(staff(role))
    assert (client.get(reverse('admin_gallery')).status_code == 200) is ok


def test_featured_patient_needs_permission_and_has_no_booking_button(clinic_profile):
    from django.core.exceptions import ValidationError
    from django.core.files.uploadedfile import SimpleUploadedFile
    from clinic.models import FeaturedPatient
    buf = io.BytesIO(); Image.new('RGB', (40, 40), 'white').save(buf, 'JPEG')
    fp = FeaturedPatient(name='A Person', profession='Actor', is_published=True,
                         photo=SimpleUploadedFile('p.jpg', buf.getvalue(), content_type='image/jpeg'))
    with pytest.raises(ValidationError):
        fp.full_clean()
    fp.consent_confirmed = True
    fp.save()
    html = Client().get(reverse('public_gallery')).content.decode()
    section = html.split('People we have cared for')[1].split('</section>')[0]
    assert 'A Person' in section and 'Actor' in section and 'Book appointment' not in section
