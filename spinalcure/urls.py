from django.urls import path, include, register_converter
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns

from django.contrib.sitemaps.views import sitemap as sitemap_view
from django.views.decorators.cache import cache_page

from . import seo
from .i18n_views import set_language
from clinic.views import clinic_portfolio_view
from payments.online_views import webhook as razorpay_webhook
from .decorators import superadmin_required
from django.views.generic import RedirectView, TemplateView
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
api_router.register(r'events', EventViewSet, basename='event')

urlpatterns = [
    # Internationalization
    path('i18n/setlang/', set_language, name='set_language'),
    path('payments/razorpay/webhook/', razorpay_webhook, name='razorpay_webhook'),
    path('robots.txt', seo.robots_txt, name='robots_txt'),
    path('sitemap.xml', cache_page(3600)(sitemap_view), {'sitemaps': seo.SITEMAPS}, name='sitemap'),
    
    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

from idcards.urls import public_urlpatterns as idcard_public_urls

urlpatterns += idcard_public_urls

urlpatterns += [
    # API Routes
    path('api/', include(api_router.urls)),
    path('api/analytics/', include('analytics.api_urls')),
]

# Localized URLs (with language prefix)
urlpatterns += i18n_patterns(
    # The public home page lives at the language root (/en/, /ta/ ...); staff sign in from the header link.
    path('', clinic_portfolio_view, name='clinic_portfolio'),
    path('accounts/', include('accounts.urls')),
    path('clinic/', include('clinic.urls')),
    path('patients/', include('patients.urls')),
    path('appointments/', include('appointments.urls')),
    path('events/', include('events.urls')),
    path('courses/', include('courses.urls')),
    path('payments/', include('payments.urls')),
    path('analytics/', include('analytics.urls')),
    path('notifications/', include('notifications.urls')),
    path('idcards/', include('idcards.urls')),
    path('ui-kit/', superadmin_required(TemplateView.as_view(template_name='ui/kit.html')), name='ui_kit'),
)

handler404 = 'spinalcure.views_errors.page_not_found'
handler500 = 'spinalcure.views_errors.server_error'

# Static and Media files
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

