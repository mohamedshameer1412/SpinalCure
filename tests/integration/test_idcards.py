"""ID cards: issuance permissions, own-card access, verification privacy, status sync, reissue."""
from datetime import date, timedelta

import pytest
from django.urls import reverse

from idcards.models import IDCard
from notifications.models import Notification


def issue(login, admin, holder, **extra):
    data = dict(user=holder.pk, card_type='staff', designation='Therapist', department='Clinical', phone='9876543210',
                joining_date='2025-01-10', blood_group='O+', emergency_contact='Ravi 9000000001')
    data.update(extra)
    return login(admin).post(reverse('idcard_issue'), data)


def test_only_admins_issue_and_numbers_are_sequential(users, login):
    assert issue(login, users['receptionist'], users['staff']).status_code == 302
    assert not IDCard.objects.exists()  # receptionist was redirected away
    issue(login, users['clinic_admin'], users['staff'])
    issue(login, users['owner'], users['owner'], card_type='owner', designation='Founder')
    numbers = sorted(IDCard.objects.values_list('card_number', flat=True))
    assert numbers == ['SC-OWN-0001', 'SC-STF-0001']
    assert Notification.objects.filter(user=users['staff'], event='idcard_issued').exists()
    # one live card per person
    issue(login, users['clinic_admin'], users['staff'])
    assert IDCard.objects.filter(user=users['staff']).count() == 1


def test_staff_see_only_their_own_card(users, login):
    issue(login, users['owner'], users['staff'])
    issue(login, users['owner'], users['doctor'])
    mine = IDCard.objects.get(user=users['staff'])
    other = IDCard.objects.get(user=users['doctor'])
    c = login(users['staff'])
    r = c.get(reverse('my_idcard'))
    assert r.status_code == 200 and mine.card_number in r.content.decode()
    assert c.get(reverse('idcard_detail', args=[mine.pk])).status_code == 200
    assert c.get(reverse('idcard_detail', args=[other.pk])).status_code == 404
    assert c.get(reverse('idcard_list')).status_code == 302


def test_public_verification_shows_no_private_data(users, login, client):
    issue(login, users['owner'], users['staff'])
    card = IDCard.objects.get()
    html = client.get(reverse('idcard_verify', args=[card.verify_token])).content.decode()
    assert 'Valid ID card' in html and card.card_number in html
    for secret in ('9876543210', 'O+', 'Ravi', users['staff'].email):
        assert secret not in html
    assert client.get(reverse('idcard_verify', args=['guess-' + 'x' * 20])).status_code == 404
    assert client.get(reverse('idcard_verify', args=[str(card.pk)])).status_code == 404  # ids are not tokens


def test_status_follows_account_expiry_and_revocation(users, login, client):
    issue(login, users['owner'], users['staff'], expiry_date=str(date.today() + timedelta(days=30)))
    card = IDCard.objects.get()
    url = reverse('idcard_verify', args=[card.verify_token])
    login(users['owner']).post(reverse('admin_user_toggle', args=[users['staff'].pk]))  # deactivate account
    card.refresh_from_db()
    assert card.status == 'suspended' and 'Valid ID card' not in client.get(url).content.decode()
    c = login(users['owner'])
    c.post(reverse('idcard_action', args=[card.pk]), {'action': 'revoke'})  # reason required
    card.refresh_from_db()
    assert card.status == 'suspended'
    c.post(reverse('idcard_action', args=[card.pk]), {'action': 'revoke', 'reason': 'Left the clinic'})
    card.refresh_from_db()
    assert card.status == 'revoked'
    c.post(reverse('idcard_action', args=[card.pk]), {'action': 'reissue'})
    card.refresh_from_db()
    assert card.status == 'revoked'  # revocation is final
    IDCard.objects.filter(pk=card.pk).update(expiry_date=date.today() - timedelta(days=1))
    assert IDCard.objects.get(pk=card.pk).effective_status == 'revoked'


def test_reissue_invalidates_old_qr(users, login, client):
    issue(login, users['owner'], users['staff'])
    card = IDCard.objects.get()
    old = card.verify_token
    login(users['owner']).post(reverse('idcard_action', args=[card.pk]), {'action': 'reissue'})
    card.refresh_from_db()
    assert card.version == 2 and card.card_number == 'SC-STF-0001'
    assert client.get(reverse('idcard_verify', args=[old])).status_code == 404
    assert client.get(reverse('idcard_verify', args=[card.verify_token])).status_code == 200


def test_verify_rate_limited(users, login, client):
    issue(login, users['owner'], users['staff'])
    token = IDCard.objects.get().verify_token
    codes = [client.get(reverse('idcard_verify', args=[token])).status_code for _ in range(31)]
    assert codes[-1] == 429


def test_share_page_has_og_tags_and_hides_invalid(users, login, client):
    issue(login, users['owner'], users['staff'])
    card = IDCard.objects.get()
    html = client.get(reverse('idcard_share', args=[card.verify_token])).content.decode()
    assert 'og:title' in html and '9876543210' not in html
    card.status = 'suspended'
    card.save()
    assert client.get(reverse('idcard_share', args=[card.verify_token])).status_code == 404


def test_card_page_renders_faces_and_qr(users, login):
    issue(login, users['owner'], users['staff'])
    html = login(users['owner']).get(reverse('idcard_detail', args=[IDCard.objects.get().pk])).content.decode()
    assert html.count('data-face="front"') == 2 and 'data:image/svg+xml;base64' in html
    assert 'rotateY(180deg)' in html and 'perspective: 1600px' in html


def test_card_requires_full_name(users, login, make_user):
    nameless = make_user('staff', email='nameless@test.com', first_name='', last_name='')
    issue(login, users['owner'], nameless)
    assert not IDCard.objects.filter(user=nameless).exists()
