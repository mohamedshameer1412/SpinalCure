"""
Custom email-based authentication backend for SpinalCure.
Allows users to log in with email + password instead of username + password.
"""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # 'username' field is used by Django's auth form — we treat it as email
        email = username or kwargs.get('email')
        if not email or not password:
            return None
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return None
        except User.MultipleObjectsReturned:
            user = User.objects.filter(email__iexact=email).order_by('id').first()

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
