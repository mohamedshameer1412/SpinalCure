"""
Django settings for SpinalCure project.
Environment-specific settings are imported based on DJANGO_ENV.
"""
import os
from .base import *

# Load environment-specific settings
_env = os.getenv('DJANGO_ENV', 'development').lower()

if _env == 'production':
    from .production import *
elif _env == 'staging':
    from .staging import *
else:
    from .development import *
