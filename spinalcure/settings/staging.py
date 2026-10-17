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
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': config('CACHE_LOCATION', default='redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# Session configuration
SESSION_CACHE_ALIAS = 'default'
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'

# Rate limiting
RATELIMIT_ENABLE = True
