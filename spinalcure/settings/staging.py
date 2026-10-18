"""
Staging settings for SpinalCure.
Similar to production with some debugging allowed.
"""
from .base import *

DEBUG = config('DEBUG', default=False, cast=bool)
SECRET_KEY = config('SECRET_KEY')
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='').split(',')

# SSL/HTTPS Settings
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# CORS - staging domain
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='https://staging.yourdomain.com').split(',')
CORS_ALLOW_CREDENTIALS = True

# Email - staging SMTP
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

# Logging - Info level for staging
LOGGING['loggers']['django']['level'] = 'INFO'
LOGGING['loggers']['spinalcure']['level'] = 'INFO'

# Cache - Redis
CACHES, _USES_REDIS = production_cache_settings()

# Session configuration
SESSION_CACHE_ALIAS = 'default'
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'

# Rate limiting
RATELIMIT_ENABLE = True


# Encryption keys must come from the environment and must not be the key that was leaked in git.
from django.core.exceptions import ImproperlyConfigured as _ImproperlyConfigured
if not FERNET_KEYS or LEAKED_DEV_FERNET_KEY in FERNET_KEYS:
    raise _ImproperlyConfigured(
        'FERNET_KEYS must be set to freshly generated key(s); the repository default key is compromised.'
    )
