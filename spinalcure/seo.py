"""Search-engine plumbing for the public site: canonical/hreflang URLs, noindex for everything private, robots.txt,
sitemap.xml and schema.org JSON-LD. Structured data describes only what is stored in the database; nothing here
claims ratings, outcomes or rankings."""
from datetime import datetime

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.http import HttpResponse
from django.urls import reverse, translate_url
from django.utils import timezone, translation
from django.views.decorators.cache import cache_page

# Only these pages may appear in search results; every other response carries X-Robots-Tag: noindex.
INDEXABLE = {
    'clinic_portfolio', 'clinic_about_page', 'public_testimonials', 'practitioner_detail',
    'public_event_list', 'event_detail', 'course_detail', 'blog_list', 'blog_detail', 'clinic_faq', 'public_gallery',
}
LANG_CODES = [code for code, _name in settings.LANGUAGES]


def site_url():
    return settings.SITE_URL.rstrip('/')


def absolute(path):
    if not path or path.startswith(('http://', 'https://')):
        return path or ''
    return f'{site_url()}{path}'


def is_indexable(request, response=None):
    match = getattr(request, 'resolver_match', None)
    if response is not None and response.status_code != 200:
        return False
    return bool(match and match.url_name in INDEXABLE)


class RobotsTagMiddleware:
    """Private pages (staff, portal, tokens, APIs) and error pages get noindex even if a link to them leaks."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not response.has_header('X-Robots-Tag') and not is_indexable(request, response):
            if request.path not in ('/robots.txt', '/sitemap.xml'):
                response['X-Robots-Tag'] = 'noindex, nofollow'
        return response


def seo(request):
    """Template context: canonical URL and hreflang alternates for indexable pages."""
    if not is_indexable(request):
        return {'seo_indexable': False}
    path = request.path
    alternates = [(code, absolute(translate_url(path, code))) for code in LANG_CODES]
    default = absolute(translate_url(path, settings.LANGUAGE_CODE))
    return {'seo_indexable': True, 'canonical_url': absolute(path), 'hreflang_alternates': alternates,
            'hreflang_default': default, 'og_locale': {'en': 'en_IN', 'ta': 'ta_IN', 'hi': 'hi_IN', 'te': 'te_IN',
                                                       'ml': 'ml_IN', 'kn': 'kn_IN'}.get(translation.get_language(), 'en_IN')}


@cache_page(3600)
def robots_txt(request):
    lines = ['User-agent: *']
    if settings.DEBUG or not getattr(settings, 'SEO_ALLOW_INDEXING', True):
        lines.append('Disallow: /')                          # staging / development: keep out of the index
    else:
        private = ['/api/', '/i18n/', '/payments/razorpay/'] + [
            f'/{code}/{area}/' for code in LANG_CODES for area in (
                'accounts', 'patients', 'appointments', 'payments', 'analytics', 'notifications', 'idcards',
                'clinic/admin', 'clinic/api', 'clinic/ajax', 'ui-kit')]
        lines += [f'Disallow: {p}' for p in private]
        lines += ['', f'Sitemap: {site_url()}/sitemap.xml']
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain; charset=utf-8')


# ── sitemap ──────────────────────────────────────────────────────────────────────────────────────────────

class _I18nSitemap(Sitemap):
    i18n = True
    alternates = True
    x_default = True
    languages = LANG_CODES

    @property
    def protocol(self):
        return 'https' if settings.SITE_URL.startswith('https') else 'http'

    def get_domain(self, site=None):
        return site_url().split('://', 1)[-1]


class StaticSitemap(_I18nSitemap):
    changefreq = 'weekly'

    def items(self):
        return ['clinic_portfolio', 'clinic_about_page', 'public_testimonials', 'clinic_faq', 'public_gallery', 'public_event_list', 'blog_list']

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        return 1.0 if item == 'clinic_portfolio' else 0.7


class BlogSitemap(_I18nSitemap):
    changefreq = 'monthly'

    def items(self):
        from clinic.blog_models import BlogPost
        return BlogPost.objects.filter(status='published').order_by('-published_at')

    def location(self, post):
        return reverse('blog_detail', args=[post.slug])

    def lastmod(self, post):
        return post.updated_at


class PractitionerSitemap(_I18nSitemap):
    def items(self):
        from clinic.models import Practitioner
        return Practitioner.objects.filter(is_active=True).order_by('-is_chief', 'name')

    def location(self, obj):
        return reverse('practitioner_detail', args=[obj.pk])


class EventSitemap(_I18nSitemap):
    def items(self):
        from events.models import Event
        return Event.objects.filter(status='published').order_by('-date')

    def location(self, obj):
        return reverse('event_detail', args=[obj.pk])


class CourseSitemap(_I18nSitemap):
    def items(self):
        from courses.models import Course
        return Course.objects.filter(is_published=True).order_by('title')

    def location(self, obj):
        return reverse('course_detail', args=[obj.pk])

    def lastmod(self, obj):
        return obj.updated_at


SITEMAPS = {'pages': StaticSitemap, 'blog': BlogSitemap, 'practitioners': PractitionerSitemap,
            'events': EventSitemap, 'courses': CourseSitemap}


# ── JSON-LD builders (plain dicts; rendered by the {% jsonld %} tag) ───────────────────────────────────────

def _img(field):
    try:
        return absolute(field.url) if field else ''
    except ValueError:
        return ''


def _clean(d):
    """Drop empty values so the markup never carries placeholder data."""
    if isinstance(d, dict):
        return {k: _clean(v) for k, v in d.items() if v not in (None, '', [], {})}
    if isinstance(d, list):
        return [_clean(v) for v in d if v not in (None, '', [], {})]
    return d


def org_ref():
    return {'@type': 'MedicalClinic', '@id': f'{site_url()}/#clinic'}


def _map_facts(clinic):
    """Coordinates and the Maps listing URL, read from the Google Maps embed the clinic pasted in its settings."""
    import re
    src = clinic.map_embed_src
    lng, lat = re.search(r'!2d(-?[\d.]+)', src), re.search(r'!3d(-?[\d.]+)', src)
    cid = re.search(r'!1s0x[0-9a-f]+(?::|%3A)0x([0-9a-f]+)', src, re.I)
    return ({'@type': 'GeoCoordinates', 'latitude': round(float(lat.group(1)), 6), 'longitude': round(float(lng.group(1)), 6)}
            if lat and lng else None,
            f'https://www.google.com/maps?cid={int(cid.group(1), 16)}' if cid else '')


def _postal_address(clinic):
    """Split the free-text address into the parts search engines read (Indian PIN code, city, state)."""
    import re
    text = ' '.join((clinic.address or '').split())
    pin = re.search(r'(\d{6})', text)
    parts = [p.strip() for p in re.sub(r'\d{6}', '', text).split(',') if p.strip()]
    state = next((p for p in parts if p.lower() in ('tamil nadu', 'tamilnadu')), '')
    city = next((p for p in parts if p.lower() in ('chennai', 'madras')), '')
    street = ', '.join(p for p in parts if p not in (state, city))
    return {'@type': 'PostalAddress', 'streetAddress': street or text, 'addressLocality': city,
            'addressRegion': state, 'postalCode': pin.group(1) if pin else '', 'addressCountry': 'IN'}


def _opening_hours():
    """OpeningHoursSpecification from the doctors' weekly shifts (the hours bookings are actually offered)."""
    try:
        from appointments.models import DoctorAvailability
    except ImportError:
        return []
    names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    spans = {}
    for a in DoctorAvailability.objects.filter(is_available=True).only('day_of_week', 'start_time', 'end_time'):
        spans.setdefault((a.start_time.strftime('%H:%M'), a.end_time.strftime('%H:%M')), set()).add(a.day_of_week)
    return [{'@type': 'OpeningHoursSpecification', 'dayOfWeek': [names[d] for d in sorted(days) if 0 <= d < 7],
             'opens': opens, 'closes': closes} for (opens, closes), days in sorted(spans.items())]


def clinic_ld(clinic):
    if clinic is None:
        return None
    geo, map_url = _map_facts(clinic)
    return _clean({
        '@context': 'https://schema.org', '@type': 'MedicalClinic', '@id': f'{site_url()}/#clinic',
        'name': clinic.name, 'description': clinic.tagline, 'url': absolute(reverse('clinic_portfolio')),
        'logo': _img(clinic.logo), 'image': _img(clinic.hero_image) or _img(clinic.logo),
        'telephone': (clinic.phone_list[0] if clinic.phone_list else ''), 'email': clinic.email,
        'address': _postal_address(clinic), 'geo': geo, 'hasMap': map_url,
        'openingHoursSpecification': _opening_hours(), 'areaServed': {'@type': 'City', 'name': 'Chennai'},
        'medicalSpecialty': 'Acupuncture',
        'foundingDate': str(clinic.established_year or ''),
        'sameAs': [u for u in (clinic.facebook, clinic.instagram, clinic.twitter, clinic.linkedin, clinic.youtube) if u],
        'availableLanguage': LANG_CODES,
    })


def practitioner_ld(p):
    return _clean({
        '@context': 'https://schema.org', '@type': 'Person', 'name': p.name, 'honorificPrefix': p.title,
        'jobTitle': p.specialization, 'description': ' '.join((p.bio or '').split())[:500], 'image': _img(p.photo),
        'url': absolute(reverse('practitioner_detail', args=[p.pk])), 'worksFor': org_ref(),
    })


def article_ld(post):
    author = post.author
    return _clean({
        '@context': 'https://schema.org', '@type': 'BlogPosting', 'headline': post.title[:110],
        'description': post.meta_description or post.excerpt, 'image': _img(post.cover_image),
        'datePublished': post.published_at.isoformat() if post.published_at else '',
        'dateModified': post.updated_at.isoformat() if post.updated_at else '',
        'author': {'@type': 'Person', 'name': post.display_author,
                   'url': absolute(reverse('practitioner_detail', args=[author.pk])) if author else ''},
        'publisher': org_ref(), 'inLanguage': getattr(post, 'language', '') or 'en',
        'mainEntityOfPage': absolute(reverse('blog_detail', args=[post.slug])),
    })


def _aware(d, t, tz_name):
    import zoneinfo
    try:
        tz = zoneinfo.ZoneInfo(tz_name or settings.TIME_ZONE)
    except Exception:
        tz = timezone.get_current_timezone()
    return datetime.combine(d, t).replace(tzinfo=tz).isoformat() if d and t else ''


def event_ld(event):
    page = absolute(reverse('event_detail', args=[event.pk]))
    # The join link is private (sent to registrants only); online events point at the public page.
    location = ({'@type': 'VirtualLocation', 'url': page} if event.is_online else
                {'@type': 'Place', 'name': event.venue, 'address': event.venue})
    fee = getattr(event, 'fees', None)
    return _clean({
        '@context': 'https://schema.org', '@type': 'Event', 'name': event.title,
        'description': ' '.join((event.description or '').split())[:500], 'image': _img(event.image),
        'startDate': _aware(event.date, event.start_time, event.timezone),
        'endDate': _aware(event.date, event.end_time, event.timezone),
        'eventStatus': 'https://schema.org/EventCancelled' if event.status == 'cancelled' else 'https://schema.org/EventScheduled',
        'eventAttendanceMode': 'https://schema.org/OnlineEventAttendanceMode' if event.is_online else 'https://schema.org/OfflineEventAttendanceMode',
        'location': location, 'organizer': org_ref(), 'inLanguage': event.language,
        'performer': {'@type': 'Person', 'name': event.presenter} if event.presenter else None,
        'offers': {'@type': 'Offer', 'price': str(fee or 0), 'priceCurrency': 'INR', 'url': page,
                   'availability': 'https://schema.org/InStock'} if event.status != 'cancelled' else None,
        'url': page,
    })


def course_ld(course):
    batches = course.batches.filter(is_published=True, is_active=True).order_by('start_date')[:5]
    page = absolute(reverse('course_detail', args=[course.pk]))
    return _clean({
        '@context': 'https://schema.org', '@type': 'Course', 'name': course.title,
        'description': course.short_description or ' '.join((course.description or '').split())[:500],
        'image': _img(course.image), 'provider': org_ref(), 'url': page,
        'offers': {'@type': 'Offer', 'price': str(course.fees or 0), 'priceCurrency': 'INR', 'category': 'Paid' if course.fees else 'Free'},
        'hasCourseInstance': [_clean({'@type': 'CourseInstance', 'name': b.name, 'startDate': b.start_date.isoformat(),
                                      'endDate': b.end_date.isoformat() if b.end_date else '',
                                      'courseMode': {'online': 'online', 'offline': 'onsite', 'hybrid': 'blended'}.get(course.platform, '')}) for b in batches],
    })


def video_ld(video):
    """Only for videos with a real thumbnail and upload date, as search engines require."""
    thumb = video.thumbnail_url
    if not thumb:
        return None
    return _clean({
        '@context': 'https://schema.org', '@type': 'VideoObject', 'name': video.title,
        'description': video.description or video.title, 'thumbnailUrl': [thumb],
        'uploadDate': video.created_at.isoformat(), 'embedUrl': video.embed_url, 'contentUrl': video.url,
    })


def faq_ld(faqs):
    """FAQPage for the questions shown on the page (published ones only, so it always matches the visible text)."""
    from clinic.content_i18n import tx
    items = [{'@type': 'Question', 'name': tx(f, 'question'),
              'acceptedAnswer': {'@type': 'Answer', 'text': ' '.join(tx(f, 'answer').split())}} for f in faqs]
    return {'@context': 'https://schema.org', '@type': 'FAQPage', 'mainEntity': items} if items else None


def breadcrumbs_ld(*crumbs):
    """crumbs: (name, path) pairs, home first."""
    return {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': i, 'name': str(name), 'item': absolute(path)}
        for i, (name, path) in enumerate(crumbs, 1)]}
