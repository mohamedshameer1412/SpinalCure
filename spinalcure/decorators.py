from django.utils.translation import gettext
from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps
from django.conf import settings
from django.http import JsonResponse
import logging

logger = logging.getLogger(__name__)

def superadmin_required(view_func):
    """Decorator for the website-management screens (clinic profile, practitioners, reviews, stories, translations).
    Granted by the `website.manage` capability (super admin, clinic admin, owner). Django's `is_staff` flag is
    deliberately ignored: it only controls the Django admin login and must not widen app permissions."""
    from spinalcure.rbac import has_capability

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not has_capability(request.user, 'website.manage'):
            messages.error(request, gettext('You do not have permission to access this section.'))
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped

def _safe_referer(request, fallback):
    """Back to the referring page only if it is on this site (no open redirect) and not this page (no loop)."""
    from django.utils.http import url_has_allowed_host_and_scheme
    ref = request.META.get('HTTP_REFERER', '')
    if (not ref or request.path in ref or not url_has_allowed_host_and_scheme(
            ref, allowed_hosts={request.get_host()}, require_https=request.is_secure())):
        return fallback
    return ref


def require_pin_auth(redirect_url_name='dashboard'):
    """
    Decorator for views that require PIN authorization for non-superadmin staff.
    Checks `auth_token` in GET or POST payload and verifies against session.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            is_superadmin = (getattr(request.user, 'role', '') == 'superadmin' or request.user.is_superuser)
            
            if is_superadmin:
                return view_func(request, *args, **kwargs)

            # Not superadmin - check token
            is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json'
            
            if request.method == 'GET':
                auth_token = request.session.get('session_security_token')

                if not auth_token:
                    if is_ajax:
                        return JsonResponse({'status': 'error', 'message': gettext('Security authorization required.')}, status=403)
                    messages.error(request, gettext('Security authorization required. Please verify your PIN first.'))
                    return redirect(_safe_referer(request, redirect_url_name))
                
                return view_func(request, *args, **kwargs)

            elif request.method == 'POST':
                submitted_token = request.POST.get('auth_token', '')
                stored_token = request.session.get('session_security_token')

                # For AJAX requests, we expect the token in POST body.
                # For standard form submissions, the token is in the session because they passed GET verification.
                auth_failed = False
                if not stored_token:
                    auth_failed = True
                elif is_ajax and submitted_token != stored_token:
                    auth_failed = True

                if auth_failed:
                    if is_ajax:
                        return JsonResponse({'status': 'error', 'message': gettext('Authorization failed. Please verify your PIN again.')}, status=403)
                    messages.error(request, gettext('Authorization failed. Please verify your PIN again.'))
                    
                    return redirect(_safe_referer(request, redirect_url_name))

                # Run the view
                response = view_func(request, *args, **kwargs)
                
                # Consume the token ONLY if the request resulted in a successful redirect 
                # (e.g. form successfully saved and redirected to detail view)
                if getattr(response, 'status_code', 200) in [301, 302]:
                    request.session['session_security_token'] = None
                    
                return response
                
        return _wrapped
    return decorator
