"""Least-privilege sweep: what can the most restricted employee role (`staff`) actually open?"""
import re

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import get_resolver, reverse
from django.urls.resolvers import URLPattern, URLResolver

User = get_user_model()


def _named_urls():
    out = []

    def walk(patterns, prefix=''):
        for p in patterns:
            if isinstance(p, URLResolver):
                walk(p.url_patterns, prefix + str(p.pattern))
            elif isinstance(p, URLPattern) and p.name:
                full = prefix + str(p.pattern)
                if not re.search(r'[<(]', full.replace('i18n', '')):
                    out.append(p.name)
    walk(get_resolver().url_patterns)
    return sorted(set(out))


# Everything a restricted employee legitimately needs.
ALLOWED = {'dashboard', 'notification_center', 'notification_summary', 'notification_preferences', 'idcard_mine', 'logout',
           # own profile, and pages/APIs that are public by design
           'auth-me', 'blog_list', 'clinic_about_page', 'clinic_portfolio', 'event-list', 'login', 'portal_login', 'settings',  # own profile
           'practitioner-list', 'public_event_list', 'public_testimonials', 'robots_txt', 'sitemap', 'clinic_faq', 'clinic_review', 'clinic_terms', 'public_gallery', 'student_signin'}
# Pages a receptionist must NOT reach (management, clinical, website and finance-admin areas).
RECEPTIONIST_BLOCKED = {'expense_list', 'expense_create', 'payments_report', 'admin_users', 'admin_activity_log', 'admin_practitioners',
                        'admin_clinic_setup', 'admin_blog_list', 'admin_testimonials', 'idcard_dashboard', 'idcard_issue',
                        'idcard_branding', 'doctor_availability', 'patient-reviews', 'event_create', 'course_create',
                        'notification_deliveries', 'export_expenses_csv', 'export_expenses_excel', 'export_expenses_pdf',
                        'export_reviews_csv', 'export_reviews_excel', 'export_reviews_pdf'}


def test_staff_role_cannot_open_business_pages():
    u = User.objects.create_user(username='sweep', email='sweep@x.com', password='x-Str0ng-pass!', role='staff')
    c = Client()
    c.force_login(u)
    opened = []
    for name in _named_urls():
        try:
            url = reverse(name)
        except Exception:
            continue
        if url.startswith(('/static', '/media', '/admin', '/i18n', '/api/schema', '/api/docs')):
            continue
        r = c.get(url, HTTP_ACCEPT='text/html')
        if r.status_code == 200 and name not in ALLOWED:
            opened.append((name, url))
    assert not opened


def test_receptionist_cannot_reach_management_areas():
    u = User.objects.create_user(username='sweep-r', email='sweep-r@x.com', password='x-Str0ng-pass!', role='receptionist')
    c = Client()
    c.force_login(u)
    reached = []
    for name in sorted(RECEPTIONIST_BLOCKED & set(_named_urls())):
        r = c.get(reverse(name), HTTP_ACCEPT='text/html')
        if r.status_code == 200:
            reached.append(name)
    assert not reached, reached


def test_profile_email_cannot_take_another_users_login():
    """Login is by email: a user must not be able to copy someone else's email onto their own account."""
    admin = User.objects.create_user(username='boss', email='boss@x.com', password='x-Str0ng-pass!', role='superadmin')
    u = User.objects.create_user(username='st', email='st@x.com', password='x-Str0ng-pass!', role='staff')
    c = Client()
    c.force_login(u)
    c.post('/en/accounts/settings/', {'first_name': 'S', 'last_name': 'T', 'email': 'BOSS@x.com', 'phone': '', 'bio': ''})
    u.refresh_from_db()
    assert u.email == 'st@x.com'
