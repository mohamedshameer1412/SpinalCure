from django.contrib.auth.models import AbstractUser
import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import timedelta
import secrets
from django.utils.crypto import salted_hmac, constant_time_compare
from spinalcure.validators import validate_phone_number
from . import roles


class CustomUser(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    """
    Custom user model with role-based access control and additional fields.
    """
    ROLE_CHOICES = roles.ROLE_CHOICES

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
    photo = models.ImageField(
        upload_to='users/',
        blank=True,
        null=True,
        verbose_name=_('Profile Photo')
    )
    bio = models.TextField(blank=True, verbose_name=_('Biography'))
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
        return self.role == roles.SUPERADMIN or self.is_superuser

    def can(self, perm):
        return roles.has_perm(self, perm)

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = roles.SUPERADMIN
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
    otp_value = models.CharField(
        max_length=64,
        verbose_name=_('OTP Hash'),
        editable=False,
        help_text=_('Keyed hash of the code; the code itself is never stored')
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
        
        otp_value = f'{secrets.randbelow(10**6):06d}'
        expires_at = now + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)
        otp_token = cls.objects.create(
            user=user,
            delivery_method=delivery_method,
            expires_at=expires_at,
            last_request_at=now,
            request_count_today=today_requests + 1,
        )
        otp_token.otp_value = otp_token._digest(otp_value)
        otp_token.save(update_fields=['otp_value'])
        created = True

        return otp_token, otp_value, created
    
    def _digest(self, code):
        return salted_hmac('accounts.otp', f'{self.pk}:{code}').hexdigest()

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
        
        otp_token = cls.objects.filter(
            user=user, delivery_method=delivery_method, is_used=False, expires_at__gt=now
        ).order_by('-created_at').first()
        if otp_token is None:
            return False, None, _('No valid OTP found. Please request a new one.')
        
        # Check if brute force attempt
        if otp_token.failed_attempts >= 5:
            otp_token.expires_at = now  # Invalidate token
            otp_token.save()
            return False, None, _('Too many failed attempts. OTP has been invalidated. Please request a new one.')
        
        is_valid = constant_time_compare(otp_token._digest(str(otp_value)), otp_token.otp_value)
        
        if not is_valid:
            otp_token.failed_attempts += 1
            otp_token.save(update_fields=['failed_attempts'])
            
            if otp_token.failed_attempts >= 5:
                return False, None, _('Too many failed attempts. OTP has been invalidated. Please request a new one.')
            
            remaining_attempts = 5 - otp_token.failed_attempts
            return False, None, _('Invalid OTP. %(n)s attempts remaining.') % {'n': remaining_attempts}
        
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
        deleted_count, _ = cls.objects.filter(
            expires_at__lt=now,
            is_used=False
        ).delete()
        return deleted_count
