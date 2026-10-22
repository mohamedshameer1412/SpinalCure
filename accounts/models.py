from django.contrib.auth.models import AbstractUser
import uuid
from django.db import models
from spinalcure.private_media import get_private_storage
from spinalcure.uploads import RandomName, SafeImageField
from spinalcure.languages import NATIVE_CHOICES
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import timedelta
import pyotp
import qrcode
from io import BytesIO
import base64
from spinalcure.validators import validate_phone_number


# Super admins, owners and clinic admins are all "the founder" on cards and in the staff list.
OWNER_ROLES = ('superadmin', 'owner', 'clinicadmin')


class CustomUser(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    """
    Custom user model with role-based access control and additional fields.
    """
    ROLE_CHOICES = [
        ('superadmin', _('Super Admin')),
        ('clinicadmin', _('Clinic Admin')),
        ('owner', _('Founder')),
        ('doctor', _('Doctor')),
        ('receptionist', _('Receptionist')),
        ('staff', _('Staff')),
    ]

    @property
    def is_owner_level(self):
        return self.role in OWNER_ROLES or self.is_superuser

    @property
    def display_role(self):
        """The role as people see it: owners, clinic admins and super admins are all just "Founder"."""
        return _('Founder') if self.is_owner_level else self.get_role_display()

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='receptionist',
        db_index=True,
        verbose_name=_('Role')
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[validate_phone_number],
        verbose_name=_('Phone')
    )
    photo = SafeImageField(
        upload_to=RandomName('users'), storage=get_private_storage,
        blank=True,
        null=True,
        verbose_name=_('Profile Photo')
    )
    bio = models.TextField(blank=True, verbose_name=_('Biography'))
    language = models.CharField(
        max_length=5,
        choices=NATIVE_CHOICES,
        default='en',
        verbose_name=_('Preferred language'),
    )
    is_verified = models.BooleanField(
        default=False,
        verbose_name=_('Email Verified'),
        db_index=True
    )

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        indexes = [
            models.Index(fields=['email', 'role']),
        ]

    def __str__(self):
        return f"{self.get_full_name() or self.email} ({self.get_role_display()})"

    @property
    def is_superadmin(self):
        """Check if user is super admin."""
        return self.role == 'superadmin' or self.is_superuser

    @property
    def is_doctor_role(self):
        """Check if user is a doctor."""
        return self.role in ('superadmin', 'doctor') or self.is_superuser

    def save(self, *args, **kwargs):
        """Enforce role-based permissions on save."""
        if self.is_superuser:
            self.role = 'superadmin'
        super().save(*args, **kwargs)


class OTPToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    """
    OTP Token model for password reset and email verification with DDoS prevention.
    Tracks failed attempts to prevent brute force attacks.
    """
    DELIVERY_CHOICES = [
        ('sms', _('SMS')),
        ('email', _('Email')),
    ]
    
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='otp_tokens',
        verbose_name=_('User')
    )
    delivery_method = models.CharField(
        max_length=10,
        choices=DELIVERY_CHOICES,
        default='email',
        verbose_name=_('Delivery Method')
    )
    otp_secret = models.CharField(
        max_length=32,
        unique=True,
        verbose_name=_('OTP Secret'),
        help_text=_('Base32 encoded secret for TOTP generation')
    )
    otp_value = models.CharField(
        max_length=6,
        verbose_name=_('Current OTP Value'),
        editable=False,
        help_text=_('Current valid OTP code')
    )
    is_used = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_('Used'),
        help_text=_('Whether this OTP has been successfully verified')
    )
    failed_attempts = models.IntegerField(
        default=0,
        verbose_name=_('Failed Verification Attempts'),
        help_text=_('Number of failed OTP verification attempts')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name=_('Created At')
    )
    expires_at = models.DateTimeField(
        db_index=True,
        verbose_name=_('Expires At'),
        help_text=_('Timestamp when OTP becomes invalid')
    )
    request_count_today = models.IntegerField(
        default=1,
        verbose_name=_('Request Count (Today)'),
        help_text=_('Number of OTP requests made today (for rate limiting)')
    )
    last_request_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Last Request At')
    )
    
    class Meta:
        verbose_name = _('OTP Token')
        verbose_name_plural = _('OTP Tokens')
        indexes = [
            models.Index(fields=['user', 'is_used']),
            models.Index(fields=['created_at']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['user', 'expires_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"OTP for {self.user.email} - {self.get_delivery_method_display()}"
    
    @staticmethod
    def _totp(secret):
        from django.conf import settings
        return pyotp.TOTP(secret, interval=settings.OTP_EXPIRY_MINUTES * 60)

    @classmethod
    def generate_otp_token(cls, user, delivery_method='email', password_reset=False):
        """
        Generate a new OTP token for the user with DDoS rate limiting.
        
        Args:
            user: CustomUser instance
            delivery_method: 'sms' or 'email'
            password_reset: Whether this is for password reset
            
        Returns:
            tuple: (OTPToken instance, OTP value, created boolean)
            
        Raises:
            PermissionError: If user has exceeded daily OTP request limit
        """
        from django.conf import settings
        
        # Check DDoS prevention: max 3 OTP requests per phone/email per hour
        now = timezone.now()
        one_hour_ago = now - timedelta(hours=1)
        recent_requests = cls.objects.filter(
            user=user,
            delivery_method=delivery_method,
            created_at__gte=one_hour_ago
        ).count()
        
        if recent_requests >= 3:
            raise PermissionError(
                _('Too many OTP requests. Please try again in 1 hour.')
            )
        
        # Check daily limit: max 5 requests per day
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_requests = cls.objects.filter(
            user=user,
            delivery_method=delivery_method,
            created_at__gte=today_start
        ).count()
        
        if today_requests >= 5:
            raise PermissionError(
                _('Daily OTP request limit exceeded. Try again tomorrow.')
            )
        
        # Invalidate previous unused OTP tokens
        cls.objects.filter(
            user=user,
            delivery_method=delivery_method,
            is_used=False,
            expires_at__gt=now
        ).update(expires_at=now)
        
        # Generate new OTP secret
        secret = pyotp.random_base32()
        totp = cls._totp(secret)
        otp_value = totp.now()
        
        # Create OTP token
        expires_at = now + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)
        # One row per request: the hourly/daily limits above count rows, and a fresh row starts with
        # failed_attempts=0 only because the previous code was invalidated, never by resetting it in place.
        otp_token = cls.objects.create(
            user=user,
            delivery_method=delivery_method,
            otp_secret=secret,
            otp_value='',  # never persist the code itself; it is derived from otp_secret
            expires_at=expires_at,
            last_request_at=now,
            request_count_today=today_requests + 1,
        )
        created = True
        
        return otp_token, otp_value, created
    
    @classmethod
    def verify_otp(cls, user, otp_value, delivery_method='email'):
        """
        Verify OTP with brute force protection (max 5 failed attempts).
        
        Args:
            user: CustomUser instance
            otp_value: OTP code submitted by user
            delivery_method: 'sms' or 'email'
            
        Returns:
            tuple: (success: bool, otp_token: OTPToken or None, error_message: str or None)
        """
        now = timezone.now()
        
        try:
            otp_token = cls.objects.get(
                user=user,
                delivery_method=delivery_method,
                is_used=False,
                expires_at__gt=now  # Not expired
            )
        except cls.DoesNotExist:
            return False, None, _('No valid OTP found. Please request a new one.')
        
        # Check if brute force attempt
        if otp_token.failed_attempts >= 5:
            otp_token.expires_at = now  # Invalidate token
            otp_token.save()
            return False, None, _('Too many failed attempts. OTP has been invalidated. Please request a new one.')
        
        # Verify OTP
        # Same interval as generation; the token's expires_at enforces the real lifetime.
        is_valid = cls._totp(otp_token.otp_secret).verify(str(otp_value).strip(), valid_window=1)
        
        if not is_valid:
            otp_token.failed_attempts += 1
            otp_token.save(update_fields=['failed_attempts'])
            
            if otp_token.failed_attempts >= 5:
                return False, None, _('Too many failed attempts. OTP has been invalidated. Please request a new one.')
            
            remaining_attempts = 5 - otp_token.failed_attempts
            return False, None, _('Invalid OTP. %(n)d attempts remaining.') % {'n': remaining_attempts}
        
        # OTP is valid
        otp_token.is_used = True
        otp_token.save(update_fields=['is_used'])
        return True, otp_token, None
    
    @classmethod
    def cleanup_expired_tokens(cls):
        """
        Delete expired OTP tokens (cleanup task for management command).
        Should be run periodically via celery or scheduled task.
        """
        now = timezone.now()
        deleted_count, _details = cls.objects.filter(
            expires_at__lt=now,
            is_used=False
        ).delete()
        return deleted_count



class StaffProfile(models.Model):
    """
    Organisational record for owners and staff. Clinical authority comes from CustomUser.role
    (a doctor can also be the owner); this model carries HR / identity data used by ID cards.
    """
    STATUS_CHOICES = [
        ('active', _('Active')),
        ('on_leave', _('On leave')),
        ('suspended', _('Suspended')),
        ('terminated', _('Terminated')),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='staff_profile')
    clinic = models.ForeignKey('clinic.ClinicProfile', on_delete=models.PROTECT, related_name='staff_profiles')
    employee_id = models.CharField(
        max_length=20, unique=True, editable=False,
        help_text=_('Immutable. Four digits and three letters, unique for everyone, e.g. 4827-KQM.'))
    designation = models.CharField(max_length=120)
    department = models.CharField(max_length=120, blank=True)
    joined_on = models.DateField()
    employment_status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='active', db_index=True)
    ended_on = models.DateField(null=True, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True, validators=[validate_phone_number])
    contact_email = models.EmailField(blank=True)
    GENDER_CHOICES = [('M', _('Male')), ('F', _('Female')), ('O', _('Other'))]
    BLOOD_CHOICES = [(b, b) for b in ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')]
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True, help_text=_('Home address, printed on the ID card.'))
    blood_group = models.CharField(max_length=5, blank=True, choices=[('', '---------')] + BLOOD_CHOICES)
    skills = models.CharField(max_length=250, blank=True)
    emergency_contact_name = models.CharField(max_length=120, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True, validators=[validate_phone_number])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['employee_id']

    def __str__(self):
        return f'{self.employee_id} — {self.user.get_full_name() or self.user.username}'

    @property
    def is_owner(self):
        return self.user.is_owner_level

    @property
    def is_employed(self):
        return self.employment_status in ('active', 'on_leave') and self.user.is_active

    @classmethod
    def _next_employee_id(cls, owner=None):
        """Four digits + three letters (no I or O), random and unique across everyone, e.g. 4827-KQM."""
        import random
        letters = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
        while True:
            code = f'{random.randint(1000, 9999)}-' + ''.join(random.choice(letters) for _ in range(3))
            if not cls.objects.filter(employee_id=code).exists():
                return code

    def save(self, *args, **kwargs):
        from django.db import IntegrityError, transaction
        if self.pk and not self._state.adding:
            original = type(self).objects.filter(pk=self.pk).values_list('employee_id', flat=True).first()
            if original and self.employee_id != original:
                raise ValueError('employee_id is immutable')
        if self.employment_status == 'terminated' and not self.ended_on:
            self.ended_on = timezone.localdate()
        if self._state.adding and not self.employee_id:
            for _attempt in range(5):  # retry on a concurrent allocation of the same number
                self.employee_id = self._next_employee_id(self.is_owner)
                try:
                    with transaction.atomic():
                        return super().save(*args, **kwargs)
                except IntegrityError:
                    self.employee_id = ''
            raise IntegrityError('Could not allocate an employee id')
        return super().save(*args, **kwargs)
