from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps
from django.conf import settings
from django.http import JsonResponse
import logging

logger = logging.getLogger(__name__)

def superadmin_required(view_func):
    """Decorator: only superadmin / staff can access these management views."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, 'You do not have permission to access this section.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped

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
                        return JsonResponse({'status': 'error', 'message': 'Security authorization required.'}, status=403)
                    messages.error(request, 'Security authorization required. Please verify your PIN first.')
                    redirect_to = request.META.get('HTTP_REFERER', redirect_url_name)
                    # Prevent endless loop if referring to itself
                    if redirect_to and request.path in redirect_to:
                        redirect_to = redirect_url_name
                    if not redirect_to:
                        redirect_to = redirect_url_name
                    return redirect(redirect_to)
                
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
                        return JsonResponse({'status': 'error', 'message': 'Authorization failed. Please verify your PIN again.'}, status=403)
                    messages.error(request, 'Authorization failed. Please verify your PIN again.')
                    
                    redirect_to = request.META.get('HTTP_REFERER', redirect_url_name)
                    if not redirect_to or request.path in redirect_to:
                        redirect_to = redirect_url_name
                    
                    return redirect(redirect_to)

                # Run the view
                response = view_func(request, *args, **kwargs)
                
                # Consume the token ONLY if the request resulted in a successful redirect 
                # (e.g. form successfully saved and redirected to detail view)
                if getattr(response, 'status_code', 200) in [301, 302]:
                    request.session['session_security_token'] = None
                    
                return response
                
        return _wrapped
    return decorator
