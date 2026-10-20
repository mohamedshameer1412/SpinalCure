"""Patient stories: review intake (consent, honeypot, timing, links, duplicates), withdrawal, moderation history,
consent-gated video publishing, focal-point crops and safe thumbnail uploads."""
import io
import json
from datetime import timedelta
from unittest import mock

import pytest
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from clinic import stories
from clinic.models import ClinicTestimonial, TestimonialModeration, TestimonialVideo

pytestmark = [pytest.mark.django_db]


def token(seconds_ago=10):
    return signing.dumps(int((timezone.now() - timedelta(seconds=seconds_ago)).timestamp()), salt=stories.FORM_SALT)


def post_review(**over):
    from django.core.cache import cache
    cache.clear()                                   # rate limit
    data = {'name': 'Kavitha', 'place': 'Anna Nagar', 'rating': 5, 'review': 'My back pain is much better now.',
            'consent': True, 'form_token': token(), 'website': ''}
    data.update(over)
    return Client().post(reverse('submit_review_ajax'), data=json.dumps(data), content_type='application/json')


@pytest.fixture
def admin(client, superuser):
    client.force_login(superuser)
    return client


def png(w=1600, h=900, colour='white'):
    buf = io.BytesIO()
    Image.new('RGB', (w, h), colour).save(buf, 'PNG')
    return SimpleUploadedFile('photo.png', buf.getvalue(), content_type='image/png')


def test_review_is_pending_with_consent_provenance_and_history(clinic_profile):
    r = post_review()
    assert r.status_code == 200 and '/reviews/withdraw/' in r.json()['withdraw_url']
    t = ClinicTestimonial.objects.get()
    assert (t.is_published, t.moderation_status, t.submitted_via, t.consent_to_publish) == (False, 'pending', 'public_form', True)
    assert t.moderation_history.get().action == 'submitted'


@pytest.mark.parametrize('over, status', [
    ({'consent': False}, 400), ({'consent': 'yes'}, 400),
    ({'review': 'Visit http://a.example and www.b.example now'}, 400), ({'rating': 9}, 400)])
def test_review_validation(clinic_profile, over, status):
    assert post_review(**over).status_code == status
    assert not ClinicTestimonial.objects.exists()


@pytest.mark.parametrize('over', [{'website': 'http://spam'}, {'form_token': 'FAST'}, {'form_token': 'forged'}])
def test_bots_get_a_success_answer_but_nothing_is_stored(clinic_profile, over):
    if over.get('form_token') == 'FAST':
        over = {'form_token': token(0)}         # built now, not at collection time
    r = post_review(**over)
    assert r.status_code == 200 and 'withdraw_url' not in r.json()
    assert not ClinicTestimonial.objects.exists()


def test_duplicate_review_is_detected_even_with_different_spacing(clinic_profile):
    assert post_review().status_code == 200
    assert post_review(review='My back pain   is much better now!!').status_code == 409
    assert ClinicTestimonial.objects.count() == 1


def test_withdrawal_unpublishes_erases_and_cannot_be_republished(clinic_profile, admin):
    url = post_review().json()['withdraw_url']
    t = ClinicTestimonial.objects.get()
    assert admin.post(reverse('admin_testimonial_moderate', args=[t.pk]), {'action': 'publish'}).status_code == 302
    t.refresh_from_db()
    assert t.is_published
    path = url.split('testserver', 1)[1]
    assert Client().get(path).status_code == 200
    assert Client().post(path).status_code == 200
    t.refresh_from_db()
    assert (t.is_published, t.moderation_status, t.review_text) == (False, 'withdrawn', '') and 'Kavitha' not in t.patient_name
    admin.post(reverse('admin_testimonial_moderate', args=[t.pk]), {'action': 'publish'})
    t.refresh_from_db()
    assert not t.is_published
    assert list(t.moderation_history.order_by('created_at').values_list('action', flat=True)) == ['submitted', 'publish', 'withdrawn']
    assert Client().get('/en/clinic/reviews/withdraw/' + 'x' * 43 + '/').status_code == 404


def test_toggle_requires_post_and_history_survives_delete(clinic_profile, admin):
    t = ClinicTestimonial.objects.create(clinic=clinic_profile, patient_name='A', review_text='Good care here.', rating=5)
    assert admin.get(reverse('admin_testimonial_toggle', args=[t.pk])).status_code == 405
    assert admin.post(reverse('admin_testimonial_toggle', args=[t.pk])).json()['is_published'] is True
    admin.post(reverse('admin_testimonial_delete', args=[t.pk]))
    assert not ClinicTestimonial.objects.exists()
    assert set(TestimonialModeration.objects.values_list('action', flat=True)) == {'publish', 'deleted'}


def test_moderation_queue_filters_and_paginates(clinic_profile, admin):
    for i in range(30):
        ClinicTestimonial.objects.create(clinic=clinic_profile, patient_name=f'P{i}', review_text='x' * 20,
                                         moderation_status='pending' if i % 2 else 'approved')
    html = admin.get(reverse('admin_testimonials') + '?status=pending').content.decode()
    assert html.count('value="reject"') == 15
    page2 = admin.get(reverse('admin_testimonials') + '?status=all&page=2').content.decode()
    assert 'Page 2 of 2' in page2 and page2.count('<article') == 6


def test_receptionist_cannot_moderate(clinic_profile, receptionist_user):
    t = ClinicTestimonial.objects.create(clinic=clinic_profile, patient_name='A', review_text='Good care here.')
    c = Client()
    c.force_login(receptionist_user)
    c.post(reverse('admin_testimonial_moderate', args=[t.pk]), {'action': 'publish'})
    t.refresh_from_db()
    assert not t.is_published


def test_video_cannot_go_live_without_consent_and_withdrawal_hides_it(admin):
    admin.post(reverse('admin_videos'), {'url': 'https://www.youtube.com/shorts/abcdefghijk', 'title': 'Disc story',
                                         'consent_status': 'unrecorded', 'is_published': 'on'})
    v = TestimonialVideo.objects.get()
    assert not v.is_published
    admin.post(reverse('admin_video_toggle', args=[v.pk]))
    v.refresh_from_db()
    assert not v.is_published
    v.consent_status = 'obtained'
    v.save()
    admin.post(reverse('admin_video_toggle', args=[v.pk]))
    v.refresh_from_db()
    assert v.is_published
    assert 'Disc story' in Client().get(reverse('public_testimonials')).content.decode()
    v.consent_status = 'withdrawn'
    v.save()
    v.refresh_from_db()
    assert not v.is_published and 'Disc story' not in Client().get(reverse('public_testimonials')).content.decode()


def test_transcript_is_searchable(admin):
    TestimonialVideo.objects.create(url='https://youtu.be/abcdefghijk', title='Story', transcript='my sciatica went away',
                                    consent_status='obtained', is_published=True)
    assert 'Story' in Client().get(reverse('public_testimonials') + '?q=sciatica').content.decode()


@pytest.mark.parametrize('aspect, fx, fy, box', [
    ('16:9', 50, 50, (0, 0, 1600, 900)),
    ('9:16', 0, 50, (0, 0, 506, 900)),          # focal at left edge: clamped, not off-image
    ('9:16', 90, 50, (1094, 0, 1600, 900)),
    ('4:5', 50, 50, (440, 0, 1160, 900))])
def test_crop_box_keeps_focal_point_inside(aspect, fx, fy, box):
    assert stories.crop_box(1600, 900, aspect, fx, fy) == box


def test_upload_creates_webp_renditions_and_rejects_non_images(admin, tmp_path):
    with override_settings(MEDIA_ROOT=tmp_path):
        v = TestimonialVideo.objects.create(url='https://youtu.be/abcdefghijk', title='S', consent_status='obtained')
        bad = SimpleUploadedFile('x.png', b'<?php echo 1; ?>', content_type='image/png')
        r = admin.post(reverse('admin_video_edit', args=[v.pk]), {'url': v.url, 'title': 'S', 'thumbnail': bad,
                                                                  'consent_status': 'obtained'}, follow=True)
        assert 'not a valid image' in r.content.decode()
        v.refresh_from_db()
        assert not v.thumbnail
        admin.post(reverse('admin_video_edit', args=[v.pk]), {'url': v.url, 'title': 'S', 'thumbnail': png(),
                                                              'consent_status': 'obtained', 'focal_x': 80, 'focal_y': 40,
                                                              'layout': '4:5', 'is_published': 'on'})
        v.refresh_from_db()
        assert v.thumbnail.name.startswith('stories/') and 'photo' not in v.thumbnail.name   # random upload name
        assert (v.focal_x, v.focal_y, v.aspect, v.thumbnail_source) == (80, 40, '4:5', 'upload')
        url = stories.rendition_url(v, '4:5', 360)
        assert url.endswith('.webp')
        with Image.open(tmp_path / url.split('/media/', 1)[1]) as img:
            assert img.size == (360, 450) and img.format == 'WEBP'
        html = Client().get(reverse('public_testimonials')).content.decode()
        assert 'type="image/webp"' in html and 'loading="lazy"' in html and 'aspect-[4/5]' in html


def test_frame_import_downloads_the_youtube_frame(admin, tmp_path):
    buf = io.BytesIO()
    Image.new('RGB', (480, 360), 'blue').save(buf, 'JPEG')
    fake = mock.MagicMock()
    fake.__enter__.return_value.read.return_value = buf.getvalue()
    with override_settings(MEDIA_ROOT=tmp_path), mock.patch('urllib.request.urlopen', return_value=fake) as m:
        v = TestimonialVideo.objects.create(url='https://youtu.be/abcdefghijk', title='S')
        admin.post(reverse('admin_video_edit', args=[v.pk]), {'url': v.url, 'title': 'S', 'thumbnail_action': 'frame2'})
        v.refresh_from_db()
    assert m.call_args[0][0].full_url == 'https://i.ytimg.com/vi/abcdefghijk/2.jpg'
    assert v.thumbnail and v.thumbnail_source == 'frame2'
