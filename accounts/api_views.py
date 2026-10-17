from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django_ratelimit.decorators import ratelimit
from django.utils.translation import gettext_lazy as _
from django.core.mail import send_mail
from django.conf import settings
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
import logging

from .models import CustomUser, OTPToken
from .serializers import (
    UserSerializer,
    OTPRequestSerializer,
    OTPVerifySerializer,
    PasswordResetConfirmSerializer
)

logger = logging.getLogger(__name__)


class OTPAuthViewSet(viewsets.ViewSet):
    """
    ViewSet for OTP-based password reset and authentication.
    Includes DDoS prevention with rate limiting.
    """
    permission_classes = [AllowAny]
    
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def request_otp(self, request):
        """
        Request OTP for password reset.
        Rate limited to 3 requests per hour per user (DDoS prevention).
        
        POST /api/auth/request-otp/
        {
            "email": "user@example.com",
            "phone": "+1234567890",
            "delivery_method": "email"  # or "sms"
        }
        """
        serializer = OTPRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            logger.warning(f'OTP request validation failed: {serializer.errors}')
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = serializer.validated_data['user']
        delivery_method = serializer.validated_data.get('delivery_method', 'email')
        
        try:
            # Generate OTP with DDoS rate limiting (max 3 per hour)
            otp_token, otp_value, created = OTPToken.generate_otp_token(
                user=user,
                delivery_method=delivery_method,
                password_reset=True
            )
            
            # Send OTP via email or SMS
            if delivery_method == 'email':
                self._send_otp_email(user, otp_value)
            elif delivery_method == 'sms':
                self._send_otp_sms(user, otp_value)
            
            logger.info(f'OTP generated for user {user.email} via {delivery_method}')
            
            return Response({
                'detail': _(f'OTP has been sent to your {delivery_method}.'),
                'delivery_method': delivery_method,
                'expires_in_minutes': settings.OTP_EXPIRY_MINUTES,
                'remaining_attempts': 5,  # Hide real attempt count for security
            }, status=status.HTTP_200_OK)
            
        except PermissionError as e:
            logger.warning(f'OTP request rate limited for user {user.email}: {str(e)}')
            return Response({
                'detail': str(e)
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)
        
        except Exception as e:
            logger.error(f'Error generating OTP for user {user.email}: {str(e)}')
            return Response({
                'detail': _('Failed to send OTP. Please try again later.')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def verify_otp(self, request):
        """
        Verify OTP and reset password.
        Rate limited to prevent brute force (5 failed attempts = OTP invalidation).
        
        POST /api/auth/verify-otp/
        {
            "email": "user@example.com",
            "otp": "123456",
            "delivery_method": "email",
            "new_password": "newpassword123",
            "confirm_password": "newpassword123"
        }
        """
        serializer = OTPVerifySerializer(data=request.data)
        
        if not serializer.is_valid():
            logger.warning(f'OTP verification failed: {serializer.errors}')
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = serializer.validated_data['user']
        new_password = serializer.validated_data['new_password']
        
        try:
            # Update user password
            user.set_password(new_password)
            user.is_verified = True
            user.save()
            
            logger.info(f'Password reset successful for user {user.email}')
            
            return Response({
                'detail': _('Password has been reset successfully. You can now log in with your new password.'),
                'user': UserSerializer(user).data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f'Error resetting password for user {user.email}: {str(e)}')
            return Response({
                'detail': _('Failed to reset password. Please try again later.')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _send_otp_email(self, user, otp_value):
        """
        Send OTP via email with professional template.
        """
        try:
            subject = f'{settings.SITE_NAME} - Password Reset Code'
            
            email_template = f"""
            <html>
                <body style="font-family: Arial, sans-serif; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto;">
                        <h2>Password Reset Request</h2>
                        
                        <p>Hello {user.get_full_name() or user.email},</p>
                        
                        <p>You requested to reset your password. Use the OTP code below to proceed:</p>
                        
                        <div style="background-color: #f0f0f0; padding: 20px; text-align: center; border-radius: 5px; margin: 20px 0;">
                            <h1 style="letter-spacing: 5px; color: #007bff;">{otp_value}</h1>
                        </div>
                        
                        <p style="color: #666;">
                            This code will expire in {settings.OTP_EXPIRY_MINUTES} minutes.
                        </p>
                        
                        <p style="color: #666; font-size: 12px;">
                            If you did not request this, please ignore this email and contact support immediately.
                        </p>
                        
                        <hr style="margin-top: 30px; border: none; border-top: 1px solid #ddd;">
                        
                        <p style="color: #999; font-size: 12px;">
                            {settings.SITE_NAME} | {settings.SITE_URL}<br>
                            For support, contact: {settings.DEFAULT_FROM_EMAIL}
                        </p>
                    </div>
                </body>
            </html>
            """
            
            send_mail(
                subject=subject,
                message=f'Your OTP is: {otp_value}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=email_template,
                fail_silently=False
            )
        except Exception as e:
            logger.error(f'Failed to send OTP email to {user.email}: {str(e)}')
            raise
    
    def _send_otp_sms(self, user, otp_value):
        """
        Send OTP via SMS (SMS gateway integration placeholder).
        To implement: Configure SMS provider (Twilio, AWS SNS, etc.)
        """
        try:
            # TODO: Integrate with SMS provider
            # Example with Twilio:
            # from twilio.rest import Client
            # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            # message = client.messages.create(
            #     body=f"Your {settings.SITE_NAME} OTP is: {otp_value}",
            #     from_=settings.TWILIO_PHONE_NUMBER,
            #     to=user.phone
            # )
            
            logger.info(f'SMS OTP would be sent to {user.phone}: {otp_value}')
            # For now, just log it (production should use real SMS service)
        except Exception as e:
            logger.error(f'Failed to send OTP SMS to {user.phone}: {str(e)}')
            raise
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """
        Get current authenticated user info.
        
        GET /api/auth/me/
        """
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
