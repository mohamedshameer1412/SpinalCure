from django.contrib.auth import views as auth_views
from django.urls import path
from .views import settings_view, RateLimitedLoginView, request_otp_view, verify_otp_view
from .admin_views import users_list, user_create, user_edit, user_toggle_active

urlpatterns = [
    # Auth Views
    path('login/', RateLimitedLoginView.as_view(), name='login'),
    path('request-otp/', request_otp_view, name='request_otp'),
    path('verify-otp/', verify_otp_view, name='verify_otp'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('settings/', settings_view, name='settings'),
    
    # Admin Views
    path('admin/users/', users_list, name='admin_users'),
    path('admin/users/create/', user_create, name='admin_user_create'),
    path('admin/users/<b64uuid:pk>/edit/', user_edit, name='admin_user_edit'),
    path('admin/users/<b64uuid:pk>/toggle/', user_toggle_active, name='admin_user_toggle'),
]
