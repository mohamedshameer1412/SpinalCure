"""Pull the clinic's YouTube channel feed (videos and Shorts, with title and caption) into the stories library.

No API key is needed: YouTube publishes a public Atom feed per channel. It lists the newest 15 uploads, so run this
often (cron / the "Sync from YouTube" button) and nothing is missed. Videos already in the library are left alone, so
staff edits (titles, thumbnails, problem tags, hidden videos) are never overwritten.
"""
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

from django.utils import timezone

from . import stories
from .models import ClinicProfile, TestimonialVideo

UA = {'User-Agent': 'Mozilla/5.0 (compatible; SpinalCureSync/1.0)'}
NS = {'a': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015', 'm': 'http://search.yahoo.com/mrss/'}
FEED = 'https://www.youtube.com/feeds/videos.xml?channel_id='


class SyncError(Exception):
    pass


def _get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            return r.read().decode('utf-8', 'replace')
    except Exception as e:                                   # network, DNS, HTTP errors: one clear message
        raise SyncError(f'Could not reach YouTube ({e}).')


def channel_id(url):
    """The UC… id for a channel URL: /channel/UC…, or looked up from an @handle / custom URL page."""
    m = re.search(r'/channel/(UC[\w-]{22})', url or '')
    if m:
        return m.group(1)
    if not re.match(r'https?://(www\.|m\.)?youtube\.com/', url or ''):
        raise SyncError('Add the YouTube channel link (https://www.youtube.com/@yourchannel) in Clinic Settings first.')
    m = re.search(r'"externalId":"(UC[\w-]{22})"|channel_id=(UC[\w-]{22})', _get(url))
    if not m:
        raise SyncError('Could not find the channel behind that link.')
    return m.group(1) or m.group(2)


def _entries(xml_text):
    root = ET.fromstring(xml_text)
    for e in root.findall('a:entry', NS):
        link = e.find('a:link[@rel="alternate"]', NS)
        desc = e.findtext('m:group/m:description', '', NS) or ''
        yield {
            'id': e.findtext('yt:videoId', '', NS),
            'title': (e.findtext('a:title', '', NS) or '').strip(),
            'url': link.get('href') if link is not None else '',
            # the first paragraph is the caption; the rest is usually opening hours and contact boilerplate
            'caption': desc.strip().split('\n\n')[0].strip()[:300],
            'published': e.findtext('a:published', '', NS),
        }


def sync(clinic=None):
    """Add new uploads as stories. Returns (added, already_there)."""
    clinic = clinic or ClinicProfile.objects.first()
    if not clinic:
        raise SyncError('No clinic profile yet.')
    try:
        items = list(_entries(_get(FEED + channel_id(clinic.youtube))))
    except ET.ParseError:
        raise SyncError('YouTube returned an unreadable feed.')
    known = set(TestimonialVideo.objects.filter(platform='youtube').values_list('video_id', flat=True))
    added = 0
    for it in items:
        if not it['id'] or it['id'] in known:
            continue
        v = TestimonialVideo(title=it['title'][:200] or 'Video', description=it['caption'], url=it['url'],
                             is_published=True)
        v.save()
        try:                                                 # a sharp stored thumbnail; the card falls back to YouTube's
            stories.import_frame(v, 'platform')
            v.save()
            stories.warm_renditions(v)
        except ValueError:
            pass
        if it['published']:                                  # keep the real upload date for ordering and display
            when = datetime.fromisoformat(it['published'])
            TestimonialVideo.objects.filter(pk=v.pk).update(created_at=when if timezone.is_aware(when) else timezone.make_aware(when))
        added += 1
    return added, len(items) - added
