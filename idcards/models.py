import re
import secrets
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# Crockford base32 without I, L, O, U: unambiguous when read aloud or typed from a printed card.
ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
CARD_ID_LENGTH = 16                      # 16 x 5 bits = 80 bits of entropy: not enumerable
_HEX = RegexValidator(r'^#[0-9A-Fa-f]{6}$', _('Use a hex colour such as #166534.'))


def new_card_id():
    return ''.join(secrets.choice(ALPHABET) for _unused in range(CARD_ID_LENGTH))


def normalise_card_id(raw):
    """Accept dashes/spaces/lower-case and the usual look-alikes (O->0, I/L->1)."""
    value = re.sub(r'[\s-]', '', (raw or '')).upper().replace('O', '0').replace('I', '1').replace('L', '1')
    return value if len(value) == CARD_ID_LENGTH and all(c in ALPHABET for c in value) else ''


def display_card_id(card_id):
    return '-'.join(card_id[i:i + 4] for i in range(0, len(card_id), 4))


class IDCardBranding(models.Model):
    """Single-clinic card branding. Use IDCardBranding.get()."""
    primary_color = models.CharField(max_length=7, default='#166534', validators=[_HEX])
    accent_color = models.CharField(max_length=7, default='#16a34a', validators=[_HEX])
    tagline = models.CharField(max_length=120, blank=True)
    org_url = models.URLField(blank=True, help_text=_('Where the QR on the back leads. Defaults to the clinic website.'))
    legal_footer = models.CharField(
        max_length=240, blank=True,
        default='This card remains the property of the issuing organisation. If found, please return it to the address above.')
    show_photo_on_verify = models.BooleanField(
        default=True, help_text=_('Show the holder photo on the public verification page (active cards only).'))

    class Meta:
        verbose_name = _('ID card branding')
        verbose_name_plural = _('ID card branding')

    @classmethod
    def get(cls):
        return cls.objects.order_by('pk').first() or cls.objects.create()


class IDCard(models.Model):
    TYPE_CHOICES = [('owner', _('Owner')), ('staff', _('Staff'))]
    STATUS_CHOICES = [('active', _('Active')), ('deactivated', _('Deactivated')), ('revoked', _('Revoked'))]
    # What verifiers and holders see; a superset of the stored status.
    EFFECTIVE = ['active', 'deactivated', 'revoked', 'expired', 'inactive']

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    card_id = models.CharField(max_length=CARD_ID_LENGTH, unique=True, editable=False, default=new_card_id)
    holder = models.ForeignKey('accounts.StaffProfile', on_delete=models.PROTECT, related_name='cards')
    card_type = models.CharField(max_length=5, choices=TYPE_CHOICES, editable=False)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='active', db_index=True)
    issued_on = models.DateField(default=timezone.localdate)
    expires_on = models.DateField(null=True, blank=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    supersedes = models.OneToOneField('self', null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name='superseded_by')
    deactivated_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='+')
    revoke_reason = models.CharField(max_length=300, blank=True)
    # What appears on the card (the holder's choice is not assumed: management decides per card).
    show_phone = models.BooleanField(default=True)
    show_email = models.BooleanField(default=False)
    show_emergency_contact = models.BooleanField(default=False)
    show_blood_group = models.BooleanField(default=True)
    show_skills = models.BooleanField(default=False)
    # Optional public sharing.
    share_enabled = models.BooleanField(default=False)
    share_token = models.CharField(max_length=43, unique=True, editable=False, default=secrets.token_urlsafe)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    IMMUTABLE = ('card_id', 'holder_id', 'card_type')

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['holder', 'status'])]
        constraints = [
            # At most one live card per person on databases with partial indexes; the service enforces it elsewhere.
            models.UniqueConstraint(fields=['holder'], condition=Q(status='active'), name='idcard_one_active_per_holder'),
        ]

    def __str__(self):
        return f'{display_card_id(self.card_id)} — {self.holder}'

    @property
    def display_id(self):
        return display_card_id(self.card_id)

    @property
    def effective_status(self):
        """Computed on every read from live data, so a stale 'active' can never be shown."""
        if self.status == 'revoked':
            return 'revoked'
        if self.status == 'deactivated':
            return 'deactivated'
        if not self.holder.is_employed:                 # account disabled or employment ended/suspended
            return 'inactive'
        if self.expires_on and self.expires_on < timezone.localdate():
            return 'expired'
        return 'active'

    @property
    def is_valid(self):
        return self.effective_status == 'active'

    def clean(self):
        if self.expires_on and self.expires_on < self.issued_on:
            raise ValidationError({'expires_on': _('Expiry cannot be before the issue date.')})

    def save(self, *args, **kwargs):
        if not self._state.adding:
            original = type(self).objects.filter(pk=self.pk).values(*self.IMMUTABLE).first()
            if original:
                for field in self.IMMUTABLE:
                    if original[field] != getattr(self, field):
                        raise ValueError(f'{field} is immutable on an issued card')
        elif not self.card_type:
            self.card_type = 'owner' if self.holder.user.role == 'owner' else 'staff'
        super().save(*args, **kwargs)


class CardVerificationLog(models.Model):
    """Audit/abuse trail for the public verification endpoint. The IP is stored only as a keyed hash."""
    card = models.ForeignKey(IDCard, null=True, blank=True, on_delete=models.SET_NULL, related_name='verifications')
    result = models.CharField(max_length=12)         # valid / invalid status name / unknown
    attempted = models.CharField(max_length=24, blank=True)
    ip_hash = models.CharField(max_length=64, db_index=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-at']
