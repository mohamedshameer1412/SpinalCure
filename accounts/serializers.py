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


class OTPRequestSerializer(serializers.Serializer):
    """
    Serializer for requesting OTP for password reset or email verification.
    Identifies user by email or phone number.
    """
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    delivery_method = serializers.ChoiceField(
        choices=['email', 'sms'],
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
        
        # Find user
        user = None
        if email:
            try:
                user = CustomUser.objects.get(email=email)
            except CustomUser.DoesNotExist:
                pass
        
        if not user and phone:
            try:
                user = CustomUser.objects.get(phone=phone)
            except CustomUser.DoesNotExist:
                pass
        
        # user is None when no account matches; the view answers identically
        # in both cases so the endpoint cannot be used to enumerate accounts.
        attrs['user'] = user
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
        choices=['email', 'sms'],
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
        
        # Find user
        user = None
        if email:
            try:
                user = CustomUser.objects.get(email=email)
            except CustomUser.DoesNotExist:
                pass
        
        if not user and phone:
            try:
                user = CustomUser.objects.get(phone=phone)
            except CustomUser.DoesNotExist:
                pass
        
        if not user:
            # Generic message: do not reveal whether an account exists.
            raise serializers.ValidationError({'otp': _('Invalid or expired OTP.')})
        
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
