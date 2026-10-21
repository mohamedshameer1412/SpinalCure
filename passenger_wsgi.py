"""Entry point for cPanel "Setup Python App" (Phusion Passenger). Passenger imports `application` from here."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_ENV', 'production')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'spinalcure.settings')

from spinalcure.wsgi import application  # noqa: E402,F401
