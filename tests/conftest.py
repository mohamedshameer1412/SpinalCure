"""Shared fixtures: one user per staff role."""
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

User = get_user_model()
PASSWORD = 'Str0ng-Pass-2026!'


@pytest.fixture(autouse=True)
def _fast_hasher(settings):
    settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']  # tests only: real hashing is slow


@pytest.fixture(autouse=True)
def _run_on_commit_now(monkeypatch):
    # Tests run inside a never-committed transaction; send outbox emails immediately, as autocommit does.
    monkeypatch.setattr('notifications.services.transaction.on_commit', lambda fn, *a, **k: fn())


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.utils import translation
    translation.activate('en')  # URLs are under /en/; LANGUAGE_CODE 'en-us' is not a URL prefix
    cache.clear()  # rate-limit counters live in the cache
    yield
    cache.clear()


@pytest.fixture
def make_user(db):
    def _make(role, **extra):
        email = extra.pop('email', f'{role}@test.com')
        extra.setdefault('first_name', role.replace('_', ' ').title())
        extra.setdefault('last_name', 'Tester')
        return User.objects.create_user(username=email, email=email, password=PASSWORD, role=role, **extra)
    return _make


@pytest.fixture
def users(make_user):
    roles = ['superadmin', 'owner', 'clinic_admin', 'doctor', 'receptionist', 'staff']
    return {r: make_user(r) for r in roles}


@pytest.fixture
def login(client):
    def _login(user):
        client.force_login(user)
        return client
    return _login
