from django_ratelimit.decorators import ratelimit
from django.contrib.auth import views as auth_views
from django.urls import path
from .views import settings_view
from .admin_views import users_list, user_create, user_edit, user_toggle_active

urlpatterns = [
    # Auth Views
    # password guessing: 10 attempts/min per IP and 20/hour per account name
    path('login/', ratelimit(key='ip', rate='10/m', method='POST', block=True)(
        ratelimit(key='post:username', rate='20/h', method='POST', block=True)(
            auth_views.LoginView.as_view(template_name='accounts/login.html'))), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('settings/', settings_view, name='settings'),
    
    # Admin Views
    path('admin/users/', users_list, name='admin_users'),
    path('admin/users/create/', user_create, name='admin_user_create'),
    path('admin/users/<b64uuid:pk>/edit/', user_edit, name='admin_user_edit'),
    path('admin/users/<b64uuid:pk>/toggle/', user_toggle_active, name='admin_user_toggle'),
]
