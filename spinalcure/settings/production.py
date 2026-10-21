"""
Production settings for SpinalCure.
Enhanced security for production deployment.
"""
from .base import *

# Security settings - MUST be configured via environment variables
DEBUG = False
SECRET_KEY = config('SECRET_KEY')  # Must be set in environment
ALLOWED_HOSTS = [h.strip() for h in config('ALLOWED_HOSTS', default='').split(',') if h.strip()]
# Forms posted from the site itself (HTTPS). Defaults to every allowed host.
CSRF_TRUSTED_ORIGINS = [o.strip() for o in config(
    'CSRF_TRUSTED_ORIGINS', default=','.join(f'https://{h.lstrip(".")}' for h in ALLOWED_HOSTS)).split(',') if o.strip()]

# SSL/HTTPS Settings
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)   # False only until AutoSSL is issued
# HTTPS-only cookies once the site is on HTTPS (with them on plain HTTP nobody could sign in)
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)  # set 0 while testing HTTPS
SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False, cast=bool)
SECURE_HSTS_PRELOAD = False
SECURE_BROWSER_XSS_FILTER = True

# CORS - production domains only
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='https://yourdomain.com').split(',')
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'content-type',
    'accept',
    'origin',
    'authorization',
]

# Email - configured for production SMTP
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_TIMEOUT = 10

# Logging - production (less verbose, only warnings/errors)
LOGGING['loggers']['django']['level'] = 'WARNING'
LOGGING['loggers']['spinalcure']['level'] = 'INFO'

# Email errors to admins
ADMINS = [('Admin', config('ADMIN_EMAIL', default='admin@spinalcure.com'))]

# Cache: Redis if CACHE_LOCATION is set, else the database cache (see base.production_cache_settings)
CACHES, _USES_REDIS = production_cache_settings()
SILENCED_SYSTEM_CHECKS = ['django_ratelimit.E003', 'django_ratelimit.W001',
                          # API-docs schema hints and deliberate HSTS choices (no preload, no subdomain lock-in)
                          'drf_spectacular.W001', 'drf_spectacular.W002', 'security.W005', 'security.W021']
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db' if _USES_REDIS else 'django.contrib.sessions.backends.db'

# Static files: collected to STATIC_ROOT and served by WhiteNoise with hashed, cache-forever names
STATIC_URL = '/static/'
STATIC_ROOT = Path(config('STATIC_ROOT', default=str(BASE_DIR / 'staticfiles')))
MIDDLEWARE = [MIDDLEWARE[0], 'whitenoise.middleware.WhiteNoiseMiddleware', *MIDDLEWARE[1:]]
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

# Uploaded files. On cPanel point MEDIA_ROOT at <document root>/media so Apache serves them directly.
MEDIA_URL = '/media/'
MEDIA_ROOT = Path(config('MEDIA_ROOT', default=str(BASE_DIR / 'media')))

# Trusted proxy headers
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PROTO = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Rate limiting enabled
RATELIMIT_ENABLE = True


# Encryption keys must come from the environment and must not be the key that was leaked in git.
from django.core.exceptions import ImproperlyConfigured as _ImproperlyConfigured
if not FERNET_KEYS or LEAKED_DEV_FERNET_KEY in FERNET_KEYS:
    raise _ImproperlyConfigured(
        'FERNET_KEYS must be set to freshly generated key(s); the repository default key is compromised.'
    )


# No browsable API in production: it renders forms for every method and widens the CSRF/HTML surface of the API.
REST_FRAMEWORK = {**REST_FRAMEWORK, 'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer']}
