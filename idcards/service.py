"""
ID card lifecycle. All authorisation is checked here as well as in the views, because these functions are
also reachable from admin tooling and tests.

* Only one live card per holder (serialised under a row lock on the holder's profile).
* Holder, card type and card id never change after issue; a "reissue" creates a NEW card id and revokes the old.
* Revocation is permanent. Deactivation is reversible (e.g. card lost, found again).
* A card is valid only while the holder's account is active and employment is active/on leave; this is computed
  at read time (IDCard.effective_status), so disabling an account or terminating employment invalidates the card
  immediately without any batch job.
"""
import logging
import secrets

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from accounts.models import StaffProfile
from notifications.service import notify, notify_staff
from spinalcure.rbac import has_capability

from .models import IDCard, display_card_id

logger = logging.getLogger(__name__)


class CardError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def _require(actor, message='You are not allowed to manage ID cards.'):
    if not has_capability(actor, 'idcards.manage'):
        raise CardError('forbidden', message)


def _safely(fn):
    try:
        return fn()
    except Exception:
        logger.exception('ID card notification failed')


def _ctx(card):
    return {'card_type': card.get_card_type_display(), 'employee_id': card.holder.employee_id}


def issue(holder, actor, *, expires_on=None, supersedes=None, **display_options):
    """Issue a card to `holder` (a StaffProfile)."""
    _require(actor)
    if holder.user.role == 'owner' and not (actor.is_superuser or actor.role in ('superadmin', 'owner', 'clinicadmin')):
        raise CardError('forbidden', 'Only management can issue an owner card.')
    allowed = {'show_phone', 'show_email', 'show_emergency_contact', 'show_blood_group', 'show_skills'}
    unknown = set(display_options) - allowed
    if unknown:
        raise CardError('invalid', f'Unknown card options: {", ".join(sorted(unknown))}')
    try:
        with transaction.atomic():
            locked = StaffProfile.objects.select_for_update().select_related('user').get(pk=holder.pk)
            if not locked.is_employed:
                raise CardError('not_employed', 'A card cannot be issued to someone whose account is disabled '
                                                'or whose employment has ended.')
            if IDCard.objects.filter(holder=locked, status__in=('active', 'deactivated')).exclude(
                    pk=getattr(supersedes, 'pk', None)).exists():
                raise CardError('exists', 'This person already has a card. Revoke it or use "Reissue".')
            card = IDCard(holder=locked, issued_by=actor, expires_on=expires_on, supersedes=supersedes,
                          **display_options)
            card.full_clean(exclude=['holder', 'issued_by', 'supersedes', 'card_type'])
            card.save()
    except IntegrityError:
        raise CardError('exists', 'This person already has an active card.')
    _safely(lambda: notify('idcard_issued', user=card.holder.user, context=_ctx(card),
                           url=reverse('idcard_mine'), dedupe_key=f'idcard:{card.pk}:issued'))
    return card


def revoke(card, actor, reason=''):
    _require(actor)
    with transaction.atomic():
        card = IDCard.objects.select_for_update().get(pk=card.pk)
        if card.status == 'revoked':
            return card
        card.status, card.revoked_at, card.revoked_by = 'revoked', timezone.now(), actor
        card.revoke_reason = (reason or '')[:300]
        card.save(update_fields=['status', 'revoked_at', 'revoked_by', 'revoke_reason', 'updated_at'])
    _announce_revoked(card)
    return card


def _announce_revoked(card):
    key = f'idcard:{card.pk}:revoked'
    _safely(lambda: notify('idcard_revoked', user=card.holder.user, context=_ctx(card),
                           url=reverse('idcard_mine'), dedupe_key=f'{key}:holder'))
    _safely(lambda: notify_staff('idcard_revoked', 'idcards.manage', context=_ctx(card),
                                 url=reverse('idcard_detail', args=[card.pk]), dedupe_key=key))


def deactivate(card, actor):
    _require(actor)
    with transaction.atomic():
        card = IDCard.objects.select_for_update().get(pk=card.pk)
        if card.status == 'revoked':
            raise CardError('revoked', 'A revoked card cannot be changed.')
        card.status, card.deactivated_at = 'deactivated', timezone.now()
        card.save(update_fields=['status', 'deactivated_at', 'updated_at'])
    return card


def reactivate(card, actor):
    _require(actor)
    with transaction.atomic():
        card = IDCard.objects.select_for_update().get(pk=card.pk)
        if card.status == 'revoked':
            raise CardError('revoked', 'A revoked card cannot be reactivated. Issue a new card instead.')
        if not card.holder.is_employed:
            raise CardError('not_employed', 'The holder is not currently employed or their account is disabled.')
        card.status, card.deactivated_at = 'active', None
        card.save(update_fields=['status', 'deactivated_at', 'updated_at'])
    return card


def reissue(card, actor, reason='Reissued', **overrides):
    """New card id for the same person; the old card is revoked in the same transaction."""
    _require(actor)
    with transaction.atomic():
        old = IDCard.objects.select_for_update().get(pk=card.pk)
        options = {k: getattr(old, k) for k in ('show_phone', 'show_email', 'show_emergency_contact',
                                                'show_blood_group', 'show_skills')}
        options.update(overrides)
        if old.status != 'revoked':
            old.status, old.revoked_at, old.revoked_by = 'revoked', timezone.now(), actor
            old.revoke_reason = (reason or 'Reissued')[:300]
            old.save(update_fields=['status', 'revoked_at', 'revoked_by', 'revoke_reason', 'updated_at'])
        new = issue(old.holder, actor, expires_on=old.expires_on, supersedes=old, **options)
    _announce_revoked(old)
    return new


def set_sharing(card, actor, enabled):
    _require(actor)
    card.share_enabled = bool(enabled)
    card.save(update_fields=['share_enabled', 'updated_at'])
    return card


def rotate_share_token(card, actor):
    """Invalidate any link already shared and create a new one."""
    _require(actor)
    card.share_token = secrets.token_urlsafe()
    card.save(update_fields=['share_token', 'updated_at'])
    return card


def cards_for_user(user):
    profile = getattr(user, 'staff_profile', None)
    if not profile:
        return IDCard.objects.none()
    return IDCard.objects.filter(holder=profile).order_by('-created_at')
