"""Safety net for large template refactors: every template compiles; every parameter-less URL answers without a 500."""
import os
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.template import engines
from django.urls import URLPattern, URLResolver, get_resolver

User = get_user_model()


def _template_names():
    roots = [Path(d) for d in settings.TEMPLATES[0]['DIRS']]
    roots += [Path(c.path) / 'templates' for c in apps.get_app_configs() if (Path(c.path) / 'templates').is_dir()]
    names = set()
    for root in roots:
        if str(root).startswith(str(settings.BASE_DIR)):                   # only our templates, not third-party apps
            for f in root.rglob('*.html'):
                names.add(str(f.relative_to(root)))
    return sorted(names)


@pytest.mark.parametrize('name', _template_names())
def test_template_compiles(name):
    engines['django'].get_template(name)


def _patterns(resolver=None, prefix=''):
    resolver = resolver or get_resolver()
    for p in resolver.url_patterns:
        route = prefix + str(p.pattern)
        if isinstance(p, URLResolver):
            yield from _patterns(p, route)
        elif isinstance(p, URLPattern):
            yield route, p


def _static_urls():
    out = []
    for route, p in _patterns():
        if '<' in route or '(' in route or '^' in route or route.startswith('admin/') or 'api/schema' in route:
            continue
        out.append('/' + route.replace('//', '/'))
    return sorted(set(out))


@pytest.fixture
def superuser(db):
    from clinic.models import ClinicProfile
    ClinicProfile.objects.create(name='Smoke Clinic', address='x', phone='9876543210')
    return User.objects.create_user(username='root', email='root@example.com', password='x', role='superadmin',
                                    is_superuser=True, is_staff=True)


@pytest.mark.parametrize('url', _static_urls())
def test_parameterless_urls_do_not_500(client, superuser, url):
    if url.startswith(('/i18n/', '/api/auth/')):
        pytest.skip('POST-only endpoints')
    client.force_login(superuser)
    r = client.get(url if not url.startswith('/en/') else url, follow=False)
    assert r.status_code < 500, f'{url} -> {r.status_code}'


def test_no_template_depends_on_a_third_party_cdn():
    """Everything the UI needs is vendored under static/, so a CDN outage or a blocked network cannot break it."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    banned = ('cdn.jsdelivr.net', 'unpkg.com', 'cdnjs.cloudflare.com', 'cdn.tailwindcss.com', 'fonts.googleapis.com',
              'fonts.gstatic.com', 'code.jquery.com')
    offenders = []
    for path in list(root.glob('templates/**/*.html')) + list(root.glob('*/templates/**/*.html')):
        if 'node_modules' in path.parts:
            continue
        text = path.read_text(encoding='utf-8', errors='ignore')
        offenders += [f'{path.relative_to(root)}: {b}' for b in banned if b in text]
    assert not offenders, offenders
