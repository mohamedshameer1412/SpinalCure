from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from spinalcure.utils import B64UUIDField
from django.contrib.auth import authenticate
from django.utils.translation import gettext_lazy as _
from .models import CustomUser, OTPToken

class UserSerializer(serializers.ModelSerializer):
    id = B64UUIDField(read_only=True)
    class Meta:
        model = CustomUser
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'role', 'phone', 'bio', 'photo')
        read_only_fields = ('id', 'role')


def _find_user(email, phone):
    qs = CustomUser.objects.filter(is_active=True)
    if email:
        return qs.filter(email__iexact=email).first()
    if phone:
        return qs.filter(phone=phone).first()
    return None


class OTPRequestSerializer(serializers.Serializer):
    """
    Serializer for requesting OTP for password reset or email verification.
    Identifies user by email or phone number.
    """
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    delivery_method = serializers.ChoiceField(
        choices=['email'],  # SMS has no configured provider yet
        default='email',
        help_text=_('Method to deliver OTP: email or SMS')
    )
    
    def validate(self, attrs):
        """Ensure either email or phone is provided."""
        email = attrs.get('email', '').strip()
        phone = attrs.get('phone', '').strip()
        
        if not email and not phone:
            raise serializers.ValidationError(
                _('Either email or phone number is required.')
            )
        
        # None when not found: the view answers identically either way (no account enumeration).
        attrs['user'] = _find_user(email, phone)
        return attrs


class OTPVerifySerializer(serializers.Serializer):
    """
    Serializer for verifying OTP and resetting password.
    """
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    otp = serializers.CharField(
        max_length=6,
        min_length=6,
        help_text=_('6-digit OTP code')
    )
    delivery_method = serializers.ChoiceField(
        choices=['email'],  # SMS has no configured provider yet
        default='email'
    )
    new_password = serializers.CharField(
        write_only=True,
        min_length=8,
        help_text=_('New password (minimum 8 characters)')
    )
    confirm_password = serializers.CharField(
        write_only=True,
        min_length=8,
        help_text=_('Confirm new password')
    )
    
    def validate(self, attrs):
        """Validate OTP and password confirmation."""
        email = attrs.get('email', '').strip()
        phone = attrs.get('phone', '').strip()
        otp = attrs.get('otp', '')
        new_password = attrs.get('new_password', '')
        confirm_password = attrs.get('confirm_password', '')
        
        # Validate password confirmation
        if new_password != confirm_password:
            raise serializers.ValidationError({
                'confirm_password': _('Passwords do not match.')
            })
        
        user = _find_user(email, phone)
        if not user:
            raise serializers.ValidationError({'otp': _('Invalid or expired code.')})
        try:
            validate_password(new_password, user)
        except DjangoValidationError as e:
            raise serializers.ValidationError({'new_password': list(e.messages)})
        
        # Verify OTP
        success, otp_token, error_message = OTPToken.verify_otp(
            user=user,
            otp_value=otp,
            delivery_method=attrs.get('delivery_method', 'email')
        )
        
        if not success:
            raise serializers.ValidationError({
                'otp': error_message
            })
        
        # Set user in validated data for use in view
        attrs['user'] = user
        attrs['otp_token'] = otp_token
        return attrs


class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Serializer for confirming password reset after OTP verification.
    """
    new_password = serializers.CharField(
        write_only=True,
        min_length=8,
        help_text=_('New password (minimum 8 characters)')
    )
    confirm_password = serializers.CharField(
        write_only=True,
        min_length=8,
        help_text=_('Confirm new password')
    )
    
    def validate(self, attrs):
        """Validate password confirmation."""
        if attrs.get('new_password') != attrs.get('confirm_password'):
            raise serializers.ValidationError({
                'confirm_password': _('Passwords do not match.')
            })
        return attrs
