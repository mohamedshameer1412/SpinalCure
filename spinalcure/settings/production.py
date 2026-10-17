"""
Production settings for SpinalCure.
Enhanced security for production deployment.
"""
from .base import *

# Security settings - MUST be configured via environment variables
DEBUG = False
SECRET_KEY = config('SECRET_KEY')  # Must be set in environment
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='').split(',')

from django.core.exceptions import ImproperlyConfigured
if not FERNET_KEYS:
    raise ImproperlyConfigured('FERNET_KEYS must be set (patient data encryption key).')

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
SECURE_CONTENT_SECURITY_POLICY = {
    'default-src': ("'self'",),
    'script-src': ("'self'", "cdn.jsdelivr.net", "cdn.tailwindcss.com"),
    'style-src': ("'self'", "'unsafe-inline'", "cdn.tailwindcss.com", "fonts.googleapis.com"),
    'font-src': ("'self'", "fonts.gstatic.com"),
    'img-src': ("'self'", "data:"),
}

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

# Cache - Redis required for production
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': config('CACHE_LOCATION', default='redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
            'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
            'IGNORE_EXCEPTIONS': True,
        }
    }
}

# Session configuration
SESSION_CACHE_ALIAS = 'default'
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'

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
