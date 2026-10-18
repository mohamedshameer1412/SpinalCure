"""Owner and staff digital ID cards."""
import secrets
from datetime import date

from django.conf import settings
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from spinalcure.validators import validate_phone_number

BLOOD_GROUPS = [(g, g) for g in ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')]


def _token():
    return secrets.token_urlsafe(24)  # 32 chars, unguessable: the QR never exposes a sequential id


class IDCard(models.Model):
    OWNER, STAFF = 'owner', 'staff'
    TYPES = [(OWNER, _('Owner')), (STAFF, _('Staff'))]
    STATUS = [('active', _('Active')), ('suspended', _('Suspended')), ('revoked', _('Revoked'))]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='id_cards')
    card_type = models.CharField(max_length=10, choices=TYPES)
    card_number = models.CharField(max_length=20, unique=True, editable=False)  # never changes, even on reissue
    designation = models.CharField(max_length=100)
    department = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True, validators=[validate_phone_number],
                             help_text=_('Shown on the card; leave empty to hide'))
    show_email = models.BooleanField(default=False, verbose_name=_('Show email on card'))
    joining_date = models.DateField()
    issue_date = models.DateField(default=date.today)
    expiry_date = models.DateField(null=True, blank=True)
    blood_group = models.CharField(max_length=3, choices=BLOOD_GROUPS, blank=True)
    emergency_contact = models.CharField(max_length=120, blank=True, help_text=_('Name and phone; printed on the back only if filled'))
    skills = models.CharField(max_length=200, blank=True)
    photo = models.ImageField(upload_to='idcards/', blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS, default='active', db_index=True)
    status_reason = models.CharField(max_length=200, blank=True)
    verify_token = models.CharField(max_length=40, unique=True, default=_token, editable=False)
    version = models.PositiveSmallIntegerField(default=1)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['card_number']
        verbose_name = _('ID card')

    def __str__(self):
        return f'{self.card_number} {self.holder_name}'

    @property
    def holder_name(self):
        return self.user.get_full_name() or 'Staff member'  # never the username: it is often an email address

    @property
    def effective_status(self):
        """Status a verifier sees; follows the account (deactivated users) and expiry automatically."""
        if self.status != 'active':
            return self.status
        if not self.user.is_active:
            return 'inactive'
        if self.expiry_date and self.expiry_date < date.today():
            return 'expired'
        return 'active'

    @property
    def is_valid(self):
        return self.effective_status == 'active'

    def save(self, *args, **kwargs):
        if not self.card_number:
            prefix = 'OWN' if self.card_type == self.OWNER else 'STF'
            with transaction.atomic():
                last = IDCard.objects.select_for_update().filter(card_number__startswith=f'SC-{prefix}-').order_by('-card_number').first()
                n = int(last.card_number.rsplit('-', 1)[1]) + 1 if last else 1
                self.card_number = f'SC-{prefix}-{n:04d}'
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    def reissue(self):
        """New QR token (old printed cards stop verifying); number stays the same."""
        self.verify_token = _token()
        self.version += 1
        self.issue_date = date.today()
        self.status, self.status_reason = 'active', ''
        self.save()
