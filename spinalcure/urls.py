from django.urls import path, include, register_converter
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from django.views.generic import RedirectView
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from .converters import B64UUIDConverter

try:
    register_converter(B64UUIDConverter, 'b64uuid')
except ValueError:
    pass

# API Routers
api_router = DefaultRouter()

# Register all API viewsets
from accounts.api_views import OTPAuthViewSet
from clinic.views import ClinicProfileViewSet, PractitionerViewSet
from patients.views import PatientViewSet, SessionViewSet
from appointments.api_views import AppointmentViewSet, DoctorAvailabilityViewSet
from payments.views import PaymentViewSet
from events.views import EventViewSet

api_router.register(r'auth', OTPAuthViewSet, basename='auth')
api_router.register(r'clinic/profiles', ClinicProfileViewSet)
api_router.register(r'clinic/practitioners', PractitionerViewSet)
api_router.register(r'patients', PatientViewSet)
api_router.register(r'sessions', SessionViewSet)
api_router.register(r'appointments', AppointmentViewSet)
api_router.register(r'availability', DoctorAvailabilityViewSet)
api_router.register(r'payments', PaymentViewSet)
api_router.register(r'events', EventViewSet)

urlpatterns = [
    # Internationalization
    path('i18n/', include('django.conf.urls.i18n')),
    
    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

urlpatterns += [
    # API Routes
    path('api/', include(api_router.urls)),
    path('api/analytics/', include('analytics.api_urls')),
]

# Localized URLs (with language prefix)
urlpatterns += i18n_patterns(
    path('', RedirectView.as_view(url='/en/accounts/login/', permanent=False), name='index'),
    path('accounts/', include('accounts.urls')),
    path('clinic/', include('clinic.urls')),
    path('patients/', include('patients.urls')),
    path('appointments/', include('appointments.urls')),
    path('events/', include('events.urls')),
    path('courses/', include('courses.urls')),
    path('payments/', include('payments.urls')),
    path('analytics/', include('analytics.urls')),
)

# Static and Media files
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

