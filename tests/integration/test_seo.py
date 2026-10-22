"""SEO: one canonical home, canonical + hreflang on public pages, noindex on everything private, valid JSON-LD
that cannot be broken out of, robots.txt, an i18n sitemap, and 404/410."""
import json
import re
from datetime import date, time
from decimal import Decimal

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from clinic.blog_models import BlogPost
from clinic.models import ClinicProfile, Practitioner

pytestmark = [pytest.mark.django_db]
SITE = dict(SITE_URL='https://www.example.org', DEBUG=False, SEO_ALLOW_INDEXING=True)


@pytest.fixture
def clinic():
    return ClinicProfile.objects.create(name='Spinal Cure', tagline='Without Surgery', address='Arumbakkam,\nChennai',
                                        phone='+914400000000', instagram='https://instagram.com/x')


def ld_blocks(html):
    return [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


@override_settings(**SITE)
def test_home_is_the_language_root_with_canonical_hreflang_and_clinic_schema(clinic):
    r = Client().get('/en/')
    html = r.content.decode()
    assert r.status_code == 200 and 'X-Robots-Tag' not in r
    assert '<link rel="canonical" href="https://www.example.org/en/">' in html
    for code in ('en', 'ta', 'hi', 'te', 'ml', 'kn'):
        assert f'hreflang="{code}" href="https://www.example.org/{code}/"' in html
    assert 'hreflang="x-default" href="https://www.example.org/en/"' in html and 'hreflang="ar"' not in html
    data = ld_blocks(html)[0]
    assert data['@type'] == 'MedicalClinic' and data['address']['streetAddress'] == 'Arumbakkam'
    assert data['address']['addressLocality'] == 'Chennai' and data['address']['addressCountry'] == 'IN'
    assert 'aggregateRating' not in data and 'review' not in data          # no self-serving rating markup
    assert Client().get('/en/clinic/portfolio/').status_code == 301


@override_settings(**SITE)
@pytest.mark.parametrize('path', ['/en/accounts/login/', '/en/patients/', '/en/payments/', '/api/patients/'])
def test_private_pages_are_noindex(path):
    r = Client().get(path)
    assert r['X-Robots-Tag'] == 'noindex, nofollow'


@override_settings(**SITE)
def test_query_strings_do_not_change_the_canonical(clinic):
    html = Client().get('/ta/clinic/testimonials/?q=back&type=videos').content.decode()
    assert '<link rel="canonical" href="https://www.example.org/ta/clinic/testimonials/">' in html


@override_settings(**SITE)
def test_robots_and_sitemap(clinic):
    robots = Client().get('/robots.txt').content.decode()
    assert 'Sitemap: https://www.example.org/sitemap.xml' in robots and 'Disallow: /en/patients/' in robots
    assert 'Disallow: /\n' not in robots
    BlogPost.objects.create(title='Posture basics', content='x', status='published')
    BlogPost.objects.create(title='Secret draft', content='x', status='draft')
    xml = Client().get('/sitemap.xml').content.decode()
    assert '<loc>https://www.example.org/en/blog/posture-basics/</loc>' in xml.replace('/clinic/blog/', '/blog/')
    assert 'hreflang="kn"' in xml and 'hreflang="x-default"' in xml and 'secret-draft' not in xml


@override_settings(DEBUG=True)
def test_staging_robots_blocks_everything():
    from django.core.cache import cache
    cache.clear()
    assert 'Disallow: /\n' in Client().get('/robots.txt').content.decode()


@override_settings(**SITE)
def test_article_schema_escapes_script_breakout(clinic):
    post = BlogPost.objects.create(title='Neck pain </script><script>alert(1)</script>', content='x', status='published')
    html = Client().get(reverse('blog_detail', args=[post.slug])).content.decode()
    assert '</script><script>alert(1)' not in html
    article = next(d for d in ld_blocks(html) if d['@type'] == 'BlogPosting')
    assert article['headline'].startswith('Neck pain </script>') and article['publisher']['@id'].endswith('/#clinic')
    assert any(d['@type'] == 'BreadcrumbList' for d in ld_blocks(html))


@override_settings(**SITE)
def test_unpublished_article_is_gone_and_unknown_is_404(clinic):
    post = BlogPost.objects.create(title='Old news', content='x', status='published')
    post.status = 'draft'
    post.save()
    assert Client().get(reverse('blog_detail', args=[post.slug])).status_code == 410
    never = BlogPost.objects.create(title='Never public', content='x', status='draft')
    assert Client().get(reverse('blog_detail', args=[never.slug])).status_code == 404
    r = Client().get('/en/no-such-page/')
    assert r.status_code == 404 and r['X-Robots-Tag'] == 'noindex, nofollow'


@override_settings(**SITE)
def test_retired_practitioner_is_gone(clinic):
    p = Practitioner.objects.create(name='Dr. A', is_active=False)
    assert Client().get(reverse('practitioner_detail', args=[p.pk])).status_code == 410
    p.is_active = True
    p.save()
    data = ld_blocks(Client().get(reverse('practitioner_detail', args=[p.pk])).content.decode())
    assert data[0]['@type'] == 'Person' and data[0]['worksFor']['@id'].endswith('/#clinic')


@override_settings(**SITE)
def test_online_event_schema_never_exposes_the_join_link(clinic):
    from events.models import Event
    e = Event.objects.create(clinic=clinic, title='Posture webinar', date=date(2030, 1, 5), start_time=time(10),
                             end_time=time(11), is_online=True, meeting_link='https://meet.example/secret',
                             status='published', fees=Decimal('0'))
    html = Client().get(reverse('event_detail', args=[e.pk])).content.decode()
    ev = next(d for d in ld_blocks(html) if d['@type'] == 'Event')
    assert ev['startDate'] == '2030-01-05T10:00:00+05:30' and ev['location']['@type'] == 'VirtualLocation'
    assert 'meet.example' not in json.dumps(ev)


def test_header_never_shows_an_unbacked_google_rating(clinic):
    assert 'on Google' not in Client().get('/en/').content.decode()
    clinic.about_stat1_number, clinic.about_stat1_label = '4.9', 'Google rating (100 reviews)'
    clinic.save()
    assert '4.9 on Google' in ' '.join(Client().get('/en/').content.decode().split())


@override_settings(**SITE)
def test_google_verification_file_is_served_for_known_tokens_only(clinic):
    c = Client()
    r = c.get('/googlefa0d02732ed9d1da.html')
    assert r.status_code == 200 and r.content.decode() == 'google-site-verification: googlefa0d02732ed9d1da.html'
    assert 'noindex' not in r.get('X-Robots-Tag', '')
    assert c.get('/google0000000000000000.html').status_code == 404


@override_settings(**SITE)
def test_home_head_carries_keywords_robots_and_social_tags(clinic):
    from clinic.models import ProblemCategory
    from django.core.cache import cache
    cache.clear()
    ProblemCategory.objects.create(name='Sciatica')
    html = Client().get('/en/').content.decode()
    assert re.search(r'<meta name="keywords" content="[^"]*classical acupuncture Chennai[^"]*Sciatica', html)
    assert 'name="robots" content="index, follow' in html and 'property="og:description"' in html and 'name="twitter:title"' in html
    robots = Client().get('/robots.txt').content.decode()
    assert 'Disallow: /private-media/' in robots and 'Sitemap: https://www.example.org/sitemap.xml' in robots


@override_settings(**SITE)
def test_bing_site_auth_file_matches_what_bing_provides(clinic):
    r = Client().get('/BingSiteAuth.xml')
    assert r.status_code == 200 and r['Content-Type'].startswith('application/xml')
    assert '<user>0BE9281E6A38622141A21E376EB36FD0</user>' in r.content.decode() and 'noindex' not in r.get('X-Robots-Tag', '')
