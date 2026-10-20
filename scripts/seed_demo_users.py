"""Create/refresh the six demo users (dev only). Run from project root: python scripts/seed_demo_users.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "spinalcure.settings")
os.environ.setdefault("DJANGO_ENV", "development")  # never seed known passwords into production
if os.environ["DJANGO_ENV"].lower() == "production":
    sys.exit("Refusing to seed demo users with DJANGO_ENV=production")

import django

django.setup()

from django.contrib.auth import get_user_model

U = get_user_model()
USERS = [
    ("admin", "admin@spinalcure.local", "Admin@12345", "superadmin"),
    ("clinicadmin", "clinicadmin@spinalcure.local", "Clinic@12345", "clinicadmin"),
    ("owner", "owner@spinalcure.local", "Owner@12345", "owner"),
    ("doctor", "doctor@spinalcure.local", "Doctor@12345", "doctor"),
    ("reception", "reception@spinalcure.local", "Recept@12345", "receptionist"),
    ("staff1", "staff1@spinalcure.local", "Staff@12345", "staff"),
]
for username, email, pw, role in USERS:
    u, _ = U.objects.get_or_create(username=username, defaults={"email": email})
    u.email, u.role, u.is_verified, u.is_active = email, role, True, True
    u.is_superuser = role == "superadmin"
    u.is_staff = role in ("superadmin", "clinicadmin")
    u.set_password(pw)
    u.save()
    print("ok", email, role)
