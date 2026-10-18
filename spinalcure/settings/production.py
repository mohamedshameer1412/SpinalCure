"""
Production settings for SpinalCure.
Enhanced security for production deployment.
"""
from .base import *

# Security settings - MUST be configured via environment variables
DEBUG = False
SECRET_KEY = config('SECRET_KEY')  # Must be set in environment
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='').split(',')

# SSL/HTTPS Settings
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
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
SILENCED_SYSTEM_CHECKS = ['django_ratelimit.E003', 'django_ratelimit.W001']
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db' if _USES_REDIS else 'django.contrib.sessions.backends.db'

# Static files - CDN ready
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
WHITENOISE = True

# Media files - upload to cloud storage recommended
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

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
