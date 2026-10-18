"""
Development settings for SpinalCure.
"""
from .base import *

DEBUG = True
SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-key-change-in-production')
ALLOWED_HOSTS = ['*']

# CORS for local development
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://localhost:5173',  # Vite dev server
]
CORS_ALLOW_CREDENTIALS = True

# Development-specific apps
INSTALLED_APPS += [
    'django_extensions',
]

# Enable debug toolbar in development
if DEBUG:
    MIDDLEWARE += [
        'django.middleware.common.CommonMiddleware',
    ]

# Security disabled for development
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0

# Email backend for development - Using SMTP instead of console to test real emails
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

# Logging - more verbose in development
LOGGING['loggers']['django']['level'] = 'DEBUG'
LOGGING['loggers']['spinalcure']['level'] = 'DEBUG'

# Cache - use local memory
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'dev-cache',
    }
}

# Ratelimit settings for development
RATELIMIT_USE_CACHE = 'default'
RATELIMIT_ENABLE = False  # Disable in local dev to avoid cache backend errors

# Internal IPs for debug toolbar
INTERNAL_IPS = ['127.0.0.1', 'localhost']

# Silence ratelimit warnings/errors in development since we use LocMemCache
SILENCED_SYSTEM_CHECKS = ["django_ratelimit.E003", "django_ratelimit.W001"]


# Local convenience only: fall back to the (compromised) repository key so dev data keeps decrypting.
if not FERNET_KEYS:
    FERNET_KEYS = [LEAKED_DEV_FERNET_KEY]
