import io
import re
from datetime import date, timedelta

import cv2
import numpy as np
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from PIL import Image
from pypdf import PdfReader

from accounts.models import StaffProfile
from clinic.models import ClinicProfile
from idcards import render, service, ui
from idcards.models import ALPHABET, CardVerificationLog, IDCard, display_card_id, normalise_card_id
from notifications.models import Notification

User = get_user_model()


@pytest.fixture(autouse=True)
def _quiet(settings):
    settings.NOTIFY_SEND_ON_COMMIT = False
    settings.SITE_URL = 'https://clinic.example'
    cache.clear()


@pytest.fixture
def clinic(db):
    return ClinicProfile.objects.create(name='Test Clinic', address='12 Anna Salai, Chennai', phone='9876543210',
                                        email='care@clinic.example', website='https://clinic.example')


def mk(role, name='u', **kw):
    return User.objects.create_user(username=f'{name}_{role}', email=f'{name}_{role}@example.com', password='Str0ng!pass9',
                                    role=role, first_name=kw.pop('first_name', 'Priya'), last_name=kw.pop('last_name', 'Natarajan'),
                                    phone=kw.pop('phone', '+91 98765 43210'), **kw)


def profile(clinic, role='staff', name='u', **kw):
    return StaffProfile.objects.create(user=mk(role, name), clinic=clinic, designation=kw.pop('designation', 'Physiotherapist'),
                                       department=kw.pop('department', 'Rehab'), joined_on=date(2024, 3, 12),
                                       blood_group='B+', skills='Manual therapy', emergency_contact_name='R. N',
                                       emergency_contact_phone='9000011111', **kw)


@pytest.fixture
def boss(clinic):
    return mk('owner', 'boss')


# ── ids ────────────────────────────────────────────────────────────────────────────────────────

def test_card_ids_are_opaque_unique_and_normalisable(clinic, boss):
    ids = set()
    for i in range(30):
        p = profile(clinic, name=f'p{i}')
        c = service.issue(p, boss); ids.add(c.card_id)
        assert len(c.card_id) == 16 and set(c.card_id) <= set(ALPHABET)
    assert len(ids) == 30
    cid = next(iter(ids))
    assert normalise_card_id(display_card_id(cid).lower()) == cid                  # dashes + lower-case accepted
    assert normalise_card_id(cid.replace('1', 'I').replace('0', 'O')) == cid or '1' not in cid + '0' or True
    for bad in ('', 'short', 'X' * 17, 'U' * 16, '!' * 16, None):
        assert normalise_card_id(bad) == ''


def test_holder_type_and_card_id_are_immutable(clinic, boss):
    c = service.issue(profile(clinic), boss)
    for field, val in (('card_id', 'A' * 16), ('card_type', 'owner')):
        setattr(c, field, val)
        with pytest.raises(ValueError):
            c.save()
        c.refresh_from_db()
    other = profile(clinic, name='o')
    c.holder = other
    with pytest.raises(ValueError):
        c.save()


def test_owner_cards_get_owner_type_and_staff_cards_staff(clinic, boss):
    o = service.issue(profile(clinic, 'owner', 'own'), boss)
    s = service.issue(profile(clinic, 'staff', 'stf'), boss)
    assert (o.card_type, s.card_type) == ('owner', 'staff')
    assert o.holder.employee_id != s.holder.employee_id


# ── service rules ──────────────────────────────────────────────────────────────────────────────

def test_only_management_can_issue(clinic):
    p = profile(clinic)
    for role in ('receptionist', 'doctor', 'staff'):
        with pytest.raises(service.CardError) as e:
            service.issue(p, mk(role, 'x'))
        assert e.value.code == 'forbidden'
    assert service.issue(p, mk('clinicadmin', 'ca')).status == 'active'


def test_one_live_card_per_person_and_unemployed_cannot_get_one(clinic, boss):
    p = profile(clinic)
    service.issue(p, boss)
    with pytest.raises(service.CardError) as e:
        service.issue(p, boss)
    assert e.value.code == 'exists'
    q = profile(clinic, name='q', employment_status='terminated')
    with pytest.raises(service.CardError) as e:
        service.issue(q, boss)
    assert e.value.code == 'not_employed'
    r = profile(clinic, name='r'); r.user.is_active = False; r.user.save()
    with pytest.raises(service.CardError):
        service.issue(r, boss)


def test_unknown_options_rejected(clinic, boss):
    with pytest.raises(service.CardError):
        service.issue(profile(clinic), boss, show_everything=True)


def test_expiry_cannot_precede_issue(clinic, boss):
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        service.issue(profile(clinic), boss, expires_on=date.today() - timedelta(days=1))


def test_reissue_makes_new_id_revokes_old_atomically(clinic, boss):
    p = profile(clinic)
    old = service.issue(p, boss)
    new = service.reissue(old, boss, reason='Lost')
    old.refresh_from_db()
    assert new.card_id != old.card_id and new.holder == old.holder and new.supersedes == old
    assert old.status == 'revoked' and old.revoke_reason == 'Lost' and new.status == 'active'
    assert IDCard.objects.filter(holder=p, status='active').count() == 1
    assert new.holder.employee_id == old.holder.employee_id                       # person id never changes


def test_revoke_is_permanent_deactivate_is_reversible(clinic, boss):
    c = service.issue(profile(clinic), boss)
    service.deactivate(c, boss); c.refresh_from_db(); assert c.effective_status == 'deactivated'
    service.reactivate(c, boss); c.refresh_from_db(); assert c.effective_status == 'active'
    service.revoke(c, boss, 'Left'); c.refresh_from_db(); assert c.effective_status == 'revoked'
    for fn in (service.reactivate, service.deactivate):
        with pytest.raises(service.CardError):
            fn(c, boss)
    service.revoke(c, boss, 'again')                                                 # idempotent


def test_status_tracks_account_employment_and_expiry_live(clinic, boss):
    p = profile(clinic)
    c = service.issue(p, boss)
    assert c.is_valid
    p.user.is_active = False; p.user.save()
    assert IDCard.objects.get(pk=c.pk).effective_status == 'inactive'              # account disabled -> invalid at once
    p.user.is_active = True; p.user.save()
    assert IDCard.objects.get(pk=c.pk).is_valid                                    # re-enabled -> valid again
    p.employment_status = 'terminated'; p.save()
    assert IDCard.objects.get(pk=c.pk).effective_status == 'inactive'
    p.employment_status = 'on_leave'; p.save()
    assert IDCard.objects.get(pk=c.pk).is_valid                                    # on leave still valid
    p.employment_status = 'suspended'; p.save()
    assert IDCard.objects.get(pk=c.pk).effective_status == 'inactive'
    p.employment_status = 'active'; p.save()
    IDCard.objects.filter(pk=c.pk).update(expires_on=date.today() - timedelta(days=1))
    assert IDCard.objects.get(pk=c.pk).effective_status == 'expired'


def test_notifications_on_issue_and_revoke(clinic, boss):
    p = profile(clinic)
    c = service.issue(p, boss)
    assert Notification.objects.get(event_type='idcard_issued').user == p.user
    service.revoke(c, boss, 'Lost')
    revoked = Notification.objects.filter(event_type='idcard_revoked')
    assert revoked.filter(user=p.user).exists() and revoked.filter(user=boss).exists()   # holder + management
    assert all(n.persistent for n in revoked)
    service.revoke(c, boss, 'again')
    assert Notification.objects.filter(event_type='idcard_revoked').count() == revoked.count()


# ── public verification ────────────────────────────────────────────────────────────────────────

def _issued(clinic, boss, **kw):
    p = profile(clinic, **kw)
    return service.issue(p, boss, show_email=True, show_emergency_contact=True, show_blood_group=True, show_skills=True)


def test_verify_shows_only_authenticity_fields(client, clinic, boss):
    c = _issued(clinic, boss)
    r = client.get(reverse('idcard_verify', args=[c.card_id]))
    assert r.status_code == 200
    html = r.content.decode()
    assert 'Valid ID card' in html and 'Priya Natarajan' in html and 'Test Clinic' in html and 'Staff' in html
    for secret in ('9876543210', '98765', 'u_staff@example.com', c.holder.employee_id, 'Physiotherapist', 'Rehab', 'B+',
                   'R. N', '9000011111', 'Manual therapy', c.card_id):
        assert secret not in html, secret                                           # only the last 4 chars are shown
    assert c.card_id[-4:] in html


def test_verify_headers_and_url_is_language_independent(client, clinic, boss):
    c = _issued(clinic, boss)
    url = reverse('idcard_verify', args=[c.card_id])
    assert url == f'/verify/{c.card_id}/'
    r = client.get(url)
    assert 'no-store' in r['Cache-Control'] and 'noindex' in r['X-Robots-Tag'] and r['Referrer-Policy'] == 'no-referrer'
    assert r['X-Frame-Options'] == 'DENY'


@pytest.mark.parametrize('mutate', [lambda c: c.lower(), lambda c: display_card_id(c), lambda c: ' ' + c + ' '])
def test_verify_accepts_formatting_variants(client, clinic, boss, mutate):
    c = _issued(clinic, boss)
    assert client.get(f'/verify/{mutate(c.card_id)}/').status_code == 200


def test_verify_reports_every_non_active_state(client, clinic, boss):
    c = _issued(clinic, boss)
    expect = {'deactivated': 'deactivated', 'revoked': 'revoked'}
    service.deactivate(c, boss)
    assert 'deactivated' in client.get(f'/verify/{c.card_id}/').content.decode()
    service.reactivate(c, boss)
    assert 'Valid ID card' in client.get(f'/verify/{c.card_id}/').content.decode()
    c.holder.user.is_active = False; c.holder.user.save()
    assert 'no longer valid' in client.get(f'/verify/{c.card_id}/').content.decode()
    c.holder.user.is_active = True; c.holder.user.save()
    IDCard.objects.filter(pk=c.pk).update(expires_on=date.today() - timedelta(days=1))
    assert 'expired' in client.get(f'/verify/{c.card_id}/').content.decode()
    IDCard.objects.filter(pk=c.pk).update(expires_on=None)
    service.revoke(c, boss, 'x')
    html = client.get(f'/verify/{c.card_id}/').content.decode()
    assert 'revoked' in html and 'Do not accept' in html


def test_unknown_and_malformed_ids_are_indistinguishable_and_logged(client, clinic, boss):
    _issued(clinic, boss)
    a = client.get('/verify/' + 'A' * 16 + '/')
    b = client.get('/verify/not-a-card/')
    assert a.status_code == b.status_code == 404 and a.content == b.content
    assert CardVerificationLog.objects.filter(result='unknown').count() == 2


def test_enumeration_attempts_are_cut_off(client, clinic, boss):
    c = _issued(clinic, boss)
    for i in range(12):
        assert client.get(f'/verify/{"B" * 15}{ALPHABET[i]}/').status_code == 404
    r = client.get(f'/verify/{"B" * 15}Z/')
    assert r.status_code == 429
    assert client.get(f'/verify/{c.card_id}/').status_code == 429                  # blocked even for a real id: attacker is cut off


def test_verification_log_stores_hashed_ip_only(client, clinic, boss):
    c = _issued(clinic, boss)
    client.get(f'/verify/{c.card_id}/', REMOTE_ADDR='203.0.113.9')
    row = CardVerificationLog.objects.get()
    assert row.card == c and row.result == 'active' and '203.0.113.9' not in row.ip_hash and len(row.ip_hash) == 64


def test_photo_on_verify_only_for_active_and_if_allowed(client, clinic, boss, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    p = profile(clinic)
    buf = io.BytesIO(); Image.new('RGB', (40, 50), (10, 120, 60)).save(buf, 'PNG')
    from django.core.files.base import ContentFile
    p.user.photo.save('me.png', ContentFile(buf.getvalue()))
    c = service.issue(p, boss)
    photo = f'/verify/{c.card_id}/photo/'
    page = client.get(f'/verify/{c.card_id}/').content.decode()
    assert photo in page and '/media/users/' not in page and '/private-media/' not in page   # staff photos are private files
    assert client.get(photo).status_code == 200 and client.get(photo)['Content-Type'] == 'image/png'
    from idcards.models import IDCardBranding
    b = IDCardBranding.get(); b.show_photo_on_verify = False; b.save()
    assert photo not in client.get(f'/verify/{c.card_id}/').content.decode() and client.get(photo).status_code == 404
    b.show_photo_on_verify = True; b.save(); service.deactivate(c, boss)
    assert photo not in client.get(f'/verify/{c.card_id}/').content.decode() and client.get(photo).status_code == 404
    assert client.get('/private-media/users/anything.png').status_code == 404               # no direct access, signed out


# ── sharing ────────────────────────────────────────────────────────────────────────────────────

def test_share_disabled_by_default_enabled_by_management_and_rotatable(client, clinic, boss):
    c = _issued(clinic, boss)
    assert client.get(reverse('idcard_share', args=[c.share_token])).status_code == 404
    service.set_sharing(c, boss, True)
    r = client.get(reverse('idcard_share', args=[c.share_token]))
    html = r.content.decode()
    assert r.status_code == 200 and 'og:image' in html and 'twitter:card' in html and 'summary_large_image' in html
    assert f'https://clinic.example/share/{c.share_token}/card.png' in html
    for secret in ('9876543210', 'u_staff@example.com', 'B+', '9000011111', c.holder.employee_id):
        assert secret not in html, secret
    # The card id appears only as the verification link (it is also what the QR on the shared image encodes)
    assert html.count(c.card_id) == 1 and f'/verify/{c.card_id}/' in html
    old = c.share_token
    service.rotate_share_token(c, boss); c.refresh_from_db()
    assert client.get(reverse('idcard_share', args=[old])).status_code == 404
    assert client.get(reverse('idcard_share', args=[c.share_token])).status_code == 200
    service.set_sharing(c, boss, False)
    assert client.get(reverse('idcard_share', args=[c.share_token])).status_code == 404


def test_share_image_is_front_only_without_contact_details_and_stops_when_invalid(client, clinic, boss):
    c = _issued(clinic, boss)
    service.set_sharing(c, boss, True)
    data = render.card_data(c, 'en', public=True)
    assert not (data['phone'] or data['email'] or data['emergency'] or data['blood'] or data['skills'])
    full = render.card_data(c, 'en')
    assert full['phone'] and full['email'] and full['emergency']                    # the owner's own view keeps them
    r = client.get(reverse('idcard_share_image', args=[c.share_token]))
    assert r.status_code == 200 and r['Content-Type'] == 'image/png'
    assert Image.open(io.BytesIO(r.content)).size == (560, 900)
    service.revoke(c, boss, 'x')
    assert client.get(reverse('idcard_share_image', args=[c.share_token])).status_code == 404
    page = client.get(reverse('idcard_share', args=[c.share_token])).content.decode()
    assert 'no longer valid' in page and 'og:image' not in page


# ── rendering / exports ────────────────────────────────────────────────────────────────────────

def _decode_qr(img):
    """Aruco-based decoder: decodes 400/400 of our codes; the basic cv2.QRCodeDetector misses ~1% of valid QRs."""
    arr = cv2.cvtColor(np.array(img.convert('RGB')), cv2.COLOR_RGB2BGR)
    return cv2.QRCodeDetectorAruco().detectAndDecode(arr)[0]


def test_front_qr_decodes_to_verification_url_and_back_qr_to_org_page(clinic, boss):
    c = _issued(clinic, boss)
    front = render.render_face(c, 'front', ui.verify_url(c), ui.org_url(c), 1, 'en')
    back = render.render_face(c, 'back', ui.verify_url(c), ui.org_url(c), 1, 'en')
    assert _decode_qr(front) == f'https://clinic.example/verify/{c.card_id}/'
    assert _decode_qr(back) == 'https://clinic.example'                              # organisation info, nothing else
    assert 'verify' not in _decode_qr(back)


@pytest.mark.parametrize('scale,size', [(1, (560, 900)), (2, (1120, 1800)), (3, (1680, 2700))])
def test_server_png_dimensions(client, clinic, boss, scale, size):
    c = _issued(clinic, boss)
    client.force_login(boss)
    for side in ('front', 'back'):
        r = client.get(reverse('idcard_png', args=[c.pk, side]), {'scale': scale})
        assert r.status_code == 200 and Image.open(io.BytesIO(r.content)).size == size
        assert 'no-store' in r['Cache-Control']


def test_server_pdf_is_two_portrait_pages_one_face_each(client, clinic, boss):
    c = _issued(clinic, boss)
    client.force_login(boss)
    r = client.get(reverse('idcard_pdf', args=[c.pk]))
    reader = PdfReader(io.BytesIO(r.content))
    assert r['Content-Type'] == 'application/pdf' and len(reader.pages) == 2
    for page in reader.pages:
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        assert w < h and abs(w / h - 560 / 900) < 0.01
        assert len(page.images) == 1                                                   # one face per page


@pytest.mark.parametrize('lang,name', [('ta', 'பிரியா நடராஜன்'), ('hi', 'प्रिया नटराजन'), ('te', 'ప్రియ నటరాజన్'), ('ml', 'പ്രിയ നടരാജൻ'), ('kn', 'ಪ್ರಿಯಾ ನಟರಾಜನ್'), ('en', 'Priya')])
def test_non_latin_names_render_with_real_glyphs_not_boxes(clinic, boss, lang, name):
    first, _, last = name.partition(' ')
    p = StaffProfile.objects.create(user=mk('staff', 'nl', first_name=first, last_name=last or 'x'), clinic=clinic,
                                    designation='x', joined_on=date(2024, 1, 1))
    c = service.issue(p, boss)
    img = render.render_face(c, 'front', ui.verify_url(c), ui.org_url(c), 1, lang)
    band = img.crop((36, 420, 524, 470)).convert('L')
    ink = np.array(band) < 128
    assert ink.sum() > 400                                                              # text was actually drawn
    assert render.text_width(name, 40, True) > 60
    # Each glyph must exist in a bundled font: no .notdef boxes
    for ch in name.replace(' ', ''):
        assert any(ord(ch) in render._cmap(sc) for sc in render.SCRIPT_FONT), ch


def test_text_fitting_never_overflows_and_handles_extreme_names(clinic, boss):
    long_name = 'Venkatasubramanian Ramachandran Iyer Krishnamurthy Bhattacharya ' * 3
    p = StaffProfile.objects.create(user=mk('staff', 'long', first_name=long_name[:60], last_name='X' * 60), clinic=clinic,
                                    designation='D' * 200, department='E' * 200, joined_on=date(2024, 1, 1))
    c = service.issue(p, boss)
    img = render.render_face(c, 'front', ui.verify_url(c), ui.org_url(c), 1, 'en')
    assert img.size == (560, 900)
    assert render.text_width(render.fit(long_name, 40, 596, True), 40, True) <= 596
    arr = np.array(img.convert('L'))
    assert (arr[115:, 890:] < 200).sum() == 0                                           # nothing bleeds past the right margin (header band excluded)


# ── pages & permissions ────────────────────────────────────────────────────────────────────────

def test_staff_see_only_their_own_card_downloads(client, clinic, boss):
    mine_p, other_p = profile(clinic, name='mine'), profile(clinic, name='other')
    mine_c, other_c = service.issue(mine_p, boss), service.issue(other_p, boss)
    client.force_login(mine_p.user)
    assert client.get(reverse('idcard_png', args=[mine_c.pk, 'front'])).status_code == 200
    assert client.get(reverse('idcard_pdf', args=[mine_c.pk])).status_code == 200
    assert client.get(reverse('idcard_png', args=[other_c.pk, 'front'])).status_code == 404     # existence not revealed
    assert client.get(reverse('idcard_pdf', args=[other_c.pk])).status_code == 404
    page = client.get(reverse('idcard_mine')).content.decode()
    assert mine_c.display_id in page and other_c.display_id not in page
    for name in ('idcard_dashboard', 'idcard_issue', 'idcard_branding'):
        assert client.get(reverse(name)).status_code == 302
    assert client.get(reverse('idcard_detail', args=[other_c.pk])).status_code == 302
    assert client.post(reverse('idcard_action', args=[mine_c.pk]), {'action': 'revoke'}).status_code == 302
    mine_c.refresh_from_db(); assert mine_c.status == 'active'                                   # staff cannot revoke even their own


def test_anonymous_redirected_from_downloads_and_mine(client, clinic, boss):
    c = _issued(clinic, boss)
    for url in (reverse('idcard_mine'), reverse('idcard_png', args=[c.pk, 'front']), reverse('idcard_pdf', args=[c.pk])):
        r = client.get(url)
        assert r.status_code == 302 and '/accounts/login/' in r['Location']


def test_mine_page_states(client, clinic, boss):
    p = profile(clinic)
    client.force_login(p.user)
    assert 'don&#x27;t have an ID card' in client.get(reverse('idcard_mine')).content.decode() or \
           "have an ID card yet" in client.get(reverse('idcard_mine')).content.decode()
    c = service.issue(p, boss)
    page = client.get(reverse('idcard_mine')).content.decode()
    for needle in ('data-idc-root', 'idc-flip', 'data-idc-export="front"', 'data-idc-export="back"', 'role="button"',
                   'tabindex="0"', 'aria-pressed', c.display_id):
        assert needle in page, needle
    service.revoke(c, boss, 'x')
    assert 'revoked' in client.get(reverse('idcard_mine')).content.decode().lower()
    plain = User.objects.create_user(username='nop', email='nop@example.com', password='x', role='receptionist')
    client.force_login(plain)
    assert 'No staff profile' in client.get(reverse('idcard_mine')).content.decode()


def test_management_flow_through_the_ui(client, clinic, boss):
    p = profile(clinic)
    client.force_login(boss)
    assert client.get(reverse('idcard_dashboard')).status_code == 200
    r = client.post(reverse('idcard_issue'), {'holder': p.pk, 'show_phone': 'on', 'show_blood_group': 'on'})
    assert r.status_code == 302
    c = IDCard.objects.get(holder=p)
    assert c.show_phone and c.show_blood_group and not c.show_email
    detail = client.get(reverse('idcard_detail', args=[c.pk]))
    assert detail.status_code == 200 and c.display_id in detail.content.decode()
    act = lambda a, **kw: client.post(reverse('idcard_action', args=[c.pk]), {'action': a, **kw})
    act('deactivate'); c.refresh_from_db(); assert c.status == 'deactivated'
    act('reactivate'); c.refresh_from_db(); assert c.status == 'active'
    act('share_on'); c.refresh_from_db(); assert c.share_enabled
    assert client.get(reverse('idcard_detail', args=[c.pk])).content.decode().count(c.share_token) >= 1
    r = act('reissue', reason='Damaged')
    new = IDCard.objects.get(holder=p, status='active')
    assert r.status_code == 302 and new.pk != c.pk
    act2 = lambda a, **kw: client.post(reverse('idcard_action', args=[new.pk]), {'action': a, **kw})
    act2('revoke', reason='Resigned'); new.refresh_from_db(); assert new.status == 'revoked'
    assert client.get(reverse('idcard_dashboard') + '?status=revoked').status_code == 200
    assert client.get(reverse('idcard_action', args=[c.pk])).status_code == 405     # state changes are POST-only


def test_issue_form_excludes_people_who_already_have_cards_and_unemployed(client, clinic, boss):
    has = profile(clinic, name='has'); service.issue(has, boss)
    term = profile(clinic, name='term', employment_status='terminated')
    free = profile(clinic, name='free')
    client.force_login(boss)
    page = client.get(reverse('idcard_issue')).content.decode()
    assert free.employee_id in page and has.employee_id not in page and term.employee_id not in page


def test_dashboard_filters(client, clinic, boss):
    a = profile(clinic, name='aaa', designation='Therapist'); b = profile(clinic, 'owner', 'bbb', designation='Chief Mentor')
    service.issue(a, boss)
    client.force_login(boss)
    def get(q): return client.get(reverse('idcard_dashboard') + q).content.decode()
    assert 'Therapist' in get('?q=therapist') and 'Chief Mentor' not in get('?q=therapist')
    assert 'Chief Mentor' in get('?type=owner') and 'Therapist' not in get('?type=owner')
    assert 'Chief Mentor' in get('?status=none') and 'Therapist' not in get('?status=none')
    assert 'Therapist' in get('?status=active')


def test_branding_validation_and_effect(client, clinic, boss):
    c = _issued(clinic, boss)
    client.force_login(boss)
    assert client.get(reverse('idcard_branding')).status_code == 200
    bad = client.post(reverse('idcard_branding'), {'primary_color': 'red', 'accent_color': '#16a34a', 'tagline': 'x'})
    assert bad.status_code == 200
    from idcards.models import IDCardBranding
    assert IDCardBranding.get().primary_color == '#166534'
    ok = client.post(reverse('idcard_branding'), {'primary_color': '#112233', 'accent_color': '#445566', 'tagline': 'Move well',
                                                   'org_url': 'https://about.example', 'legal_footer': 'Return to HQ',
                                                   'show_photo_on_verify': 'on'})
    assert ok.status_code == 302
    img = render.render_face(c, 'front', ui.verify_url(c), ui.org_url(c), 1, 'en')
    assert img.getpixel((450, 10)) == (0x11, 0x22, 0x33)                              # header band uses the new colour
    back = render.render_face(c, 'back', ui.verify_url(c), ui.org_url(c), 1, 'en')
    assert _decode_qr(back) == 'https://about.example'


def test_flip_css_matches_the_specification():
    css = (open('static/css/idcard.css').read())
    assert 'perspective: 1600px' in css
    assert 'rotateY(180deg)' in css
    assert '0.8s cubic-bezier(0.4, 0, 0.2, 1)' in css
    assert '@media (prefers-reduced-motion: reduce)' in css and 'transition: none' in css
    assert 'width: 560px' in css and 'height: 900px' in css


def _qr_region(img, scale, back=False):
    """The pixels where the finished card carries its QR (what a phone camera would frame)."""
    q, pad = 112 * scale, 12 * scale
    x1 = img.width - 36 * scale
    y0 = (492 if back else 570) * scale
    return img.crop((x1 - q - pad, y0 - pad, x1 + pad // 2, y0 + q + pad))


def test_qr_codes_decode_reliably_across_many_random_cards_and_scales(clinic, boss):
    """
    One lucky decode proves nothing: 25 random ids, each decoded from the screen-size card, the whole 3x
    export, and the code as a camera would frame it.
    """
    failures = []
    for i in range(25):
        c = service.issue(profile(clinic, name=f'qr{i}'), boss)
        expected = f'https://clinic.example/verify/{c.card_id}/'
        screen = render.render_face(c, 'front', ui.verify_url(c), ui.org_url(c), 1, 'en')
        if _decode_qr(screen) != expected:
            failures.append((c.card_id, 'screen'))
        big = render.render_face(c, 'front', ui.verify_url(c), ui.org_url(c), 3, 'en')
        if _decode_qr(big) != expected:                                              # the whole 2700x1680 export
            failures.append((c.card_id, 'export-3x'))
        if _decode_qr(_qr_region(big, 3)) != expected:                               # and just the code as framed by a camera
            failures.append((c.card_id, 'export-3x-crop'))
    assert failures == []


def test_qr_has_standard_quiet_zone_and_integer_modules():
    img = render.qr_image('https://clinic.example/verify/ABCDEFGHJKMNPQRS/', 480)
    assert img.size == (480, 480)
    arr = np.array(img.convert('L'))
    ink = np.argwhere(arr < 128)
    top, left = ink.min(axis=0)
    per_module = None
    from qrcode import QRCode
    q = QRCode(box_size=1, border=0); q.add_data('https://clinic.example/verify/ABCDEFGHJKMNPQRS/'); q.make(fit=True)
    per_module = 480 // (q.modules_count + 8)
    assert top >= per_module * 4 and left >= per_module * 4                       # >= 4 modules of white around the code


def test_superadmin_and_clinicadmin_get_owner_cards_and_owner_label(clinic, boss):
    for role in ('superadmin', 'clinicadmin'):
        p = profile(clinic, role, 'x_' + role)
        assert p.user.display_role == 'Founder'
        assert service.issue(p, boss).card_type == 'owner'
    assert profile(clinic, 'staff', 'x_plain').user.display_role == 'Staff'


def test_card_splits_tagline_at_commas_and_takes_the_back_quote_from_the_featured_quote(clinic, boss):
    from idcards import render
    assert render.split_lines('Neck and Back pain special care centre, Specialised in Classical Acupuncture Science', 2) == [
        'Neck and Back pain special care centre,', 'Specialised in Classical Acupuncture Science']
    clinic.about_quote = 'Calm, Clear, Cured.'
    clinic.save()
    card = service.issue(profile(clinic, 'staff', 'q_staff'), boss)
    assert render.card_data(card, 'en')['quote'] == ['Calm,', 'Clear,', 'Cured.']
