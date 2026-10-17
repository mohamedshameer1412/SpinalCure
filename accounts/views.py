from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect

from spinalcure.utils import rate_limited, client_ip
from spinalcure.validators import validate_phone_number
from .models import CustomUser, OTPToken
from .serializers import _find_user, OTPVerifySerializer


class RateLimitedLoginView(LoginView):
    """Staff login, limited per IP and per account to slow password guessing."""
    template_name = 'accounts/login.html'

    def post(self, request, *args, **kwargs):
        email = request.POST.get('username', '').strip().lower()
        if rate_limited(f'login_ip:{client_ip(request)}', 30, 900) or rate_limited(f'login_user:{email}', 10, 900):
            form = self.get_form()
            return self.render_to_response(self.get_context_data(form=form, rate_limited=True), status=429)
        return super().post(request, *args, **kwargs)


def request_otp_view(request):
    """Forgot password step 1. Same response whether or not the email exists."""
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        user = _find_user(email, None)
        if user and not rate_limited(f'otp_ip:{client_ip(request)}', 10, 3600):
            try:
                _token, code, _created = OTPToken.generate_otp_token(user, 'email', password_reset=True)
                from .api_views import send_otp_email
                send_otp_email(user, code)
            except PermissionError:
                pass  # per-user hourly/daily limit reached; answer stays generic
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Password reset email failed for user %s', user.pk)
        request.session['reset_email'] = email
        messages.info(request, 'If an account exists for that email, a 6-digit code has been sent to it.')
        return redirect('verify_otp')
    return render(request, 'accounts/password_reset.html', {'step': 'request'})


def verify_otp_view(request):
    """Forgot password step 2: code + new password (validated by the same serializer as the API)."""
    email = request.session.get('reset_email')
    if not email:
        return redirect('request_otp')
    errors = []
    if request.method == 'POST':
        if rate_limited(f'otp_verify_ip:{client_ip(request)}', 20, 3600):
            errors.append('Too many attempts. Please try again later.')
        else:
            s = OTPVerifySerializer(data={
                'email': email, 'otp': request.POST.get('otp', '').strip(), 'delivery_method': 'email',
                'new_password': request.POST.get('new_password', ''), 'confirm_password': request.POST.get('confirm_password', ''),
            })
            if s.is_valid():
                user = s.validated_data['user']
                user.set_password(s.validated_data['new_password'])
                user.save(update_fields=['password'])
                del request.session['reset_email']
                messages.success(request, 'Your password has been reset. Please sign in.')
                return redirect('login')
            for field_errors in s.errors.values():
                errors.extend(str(e) for e in (field_errors if isinstance(field_errors, list) else [field_errors]))
    return render(request, 'accounts/password_reset.html', {'step': 'verify', 'errors': errors})


@login_required
def settings_view(request):
    user = request.user
    if request.method == 'POST':
        email = request.POST.get('email', user.email).strip()
        phone = request.POST.get('phone', user.phone).strip()
        error = None
        if email and CustomUser.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
            error = 'Another account already uses this email address.'
        elif phone:
            try:
                validate_phone_number(phone)
            except ValidationError as e:
                error = e.messages[0]
        if error:
            messages.error(request, error)
        else:
            user.first_name = request.POST.get('first_name', user.first_name).strip()
            user.last_name = request.POST.get('last_name', user.last_name).strip()
            user.email = email
            user.phone = phone
            user.bio = request.POST.get('bio', user.bio)
            user.save()
            messages.success(request, 'Profile updated successfully!')
        return redirect('settings')

    return render(request, 'accounts/settings.html', {'user': user})
