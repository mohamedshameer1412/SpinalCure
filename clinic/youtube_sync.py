"""Pull the clinic's YouTube channel into the stories library (videos and Shorts, with title, caption and tags).

Two ways, picked automatically:
  * with YOUTUBE_API_KEY (free YouTube Data API v3 key): every upload, tags included; ~1 quota unit per 50 videos.
  * without a key: YouTube's public Atom feed, which lists only the newest 15 uploads.
Videos already in the library are never overwritten: staff edits (titles, thumbnails, hidden videos) win and only
blank caption/tags/problem fields are filled. New uploads are sorted into a problem by matching the problem's
name or keywords against the video's tags, title and caption.
"""
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlencode

from django.conf import settings
from django.utils import timezone

from . import stories
from .models import ClinicProfile, ProblemCategory, TestimonialVideo

UA = {'User-Agent': 'Mozilla/5.0 (compatible; SpinalCureSync/1.0)'}
NS = {'a': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015', 'm': 'http://search.yahoo.com/mrss/'}
FEED = 'https://www.youtube.com/feeds/videos.xml?channel_id='


class SyncError(Exception):
    pass


def _get(url, method='GET'):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA, method=method), timeout=20) as r:
            return r.read().decode('utf-8', 'replace')
    except Exception as e:                                   # network, DNS, HTTP errors: one clear message
        raise SyncError(f'Could not reach YouTube ({e}).')


def channel_id(url):
    """The UC... id for a channel URL: /channel/UC..., or looked up from an @handle / custom URL page."""
    m = re.search(r'/channel/(UC[\w-]{22})', url or '')
    if m:
        return m.group(1)
    if not re.match(r'https?://(www\.|m\.)?youtube\.com/', url or ''):
        raise SyncError('Add the YouTube channel link (https://www.youtube.com/@yourchannel) in Clinic Settings first.')
    m = re.search(r'"externalId":"(UC[\w-]{22})"|channel_id=(UC[\w-]{22})', _get(url))
    if not m:
        raise SyncError('Could not find the channel behind that link.')
    return m.group(1) or m.group(2)


def _caption(text):
    # the first paragraph is the caption; the rest is usually opening hours and contact boilerplate
    return (text or '').strip().split('\n\n')[0].strip()[:300]


def _feed_entries(cid):
    root = ET.fromstring(_get(FEED + cid))
    for e in root.findall('a:entry', NS):
        link = e.find('a:link[@rel="alternate"]', NS)
        yield {'id': e.findtext('yt:videoId', '', NS), 'title': (e.findtext('a:title', '', NS) or '').strip(),
               'url': link.get('href') if link is not None else '',
               'caption': _caption(e.findtext('m:group/m:description', '', NS)),
               'published': e.findtext('a:published', '', NS), 'tags': '', 'duration': ''}


def _api(path, **params):
    return json.loads(_get(f'https://www.googleapis.com/youtube/v3/{path}?' + urlencode({**params, 'key': settings.YOUTUBE_API_KEY})))


def _api_entries(cid):
    uploads = 'UU' + cid[2:]                                  # a channel's uploads playlist id
    page = None
    while True:
        params = {'part': 'contentDetails', 'playlistId': uploads, 'maxResults': 50}
        if page:
            params['pageToken'] = page
        data = _api('playlistItems', **params)
        ids = [i['contentDetails']['videoId'] for i in data.get('items', [])]
        if ids:
            for v in _api('videos', part='snippet,contentDetails', id=','.join(ids)).get('items', []):
                sn = v['snippet']
                yield {'id': v['id'], 'title': sn.get('title', '').strip(), 'url': f"https://www.youtube.com/watch?v={v['id']}",
                       'caption': _caption(sn.get('description')), 'published': sn.get('publishedAt', '').replace('Z', '+00:00'),
                       'tags': ', '.join(sn.get('tags', []))[:500], 'duration': v['contentDetails'].get('duration', '')}
        page = data.get('nextPageToken')
        if not page:
            return


def _is_short(item):
    """A video of three minutes or less whose /shorts/ page does not bounce back to /watch."""
    if '/shorts/' in item['url']:
        return True
    m = re.fullmatch(r'PT(?:(\d+)M)?(?:(\d+)S)?', item.get('duration', ''))
    if not m:
        return False
    secs = int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
    if secs > 180:
        return False
    try:
        req = urllib.request.Request('https://www.youtube.com/shorts/' + item['id'], headers=UA, method='HEAD')
        with urllib.request.urlopen(req, timeout=15) as r:
            return '/shorts/' in r.geturl()
    except Exception:
        return secs <= 60


def match_problem(text):
    """The first active problem whose name or keywords appear in the text (tags, title, caption)."""
    low = (text or '').lower()
    for p in ProblemCategory.objects.filter(is_active=True):
        words = [p.name.lower().split(' & ')[0].strip()] + [k.strip().lower() for k in p.keywords.split(',') if k.strip()]
        if any(w and w in low for w in words):
            return p
    return None


def sync(clinic=None):
    """Add new uploads as stories and fill blanks on existing ones. Returns (added, already_there)."""
    clinic = clinic or ClinicProfile.objects.first()
    if not clinic:
        raise SyncError('No clinic profile yet.')
    try:
        cid = channel_id(clinic.youtube)
        items = list(_api_entries(cid)) if settings.YOUTUBE_API_KEY else list(_feed_entries(cid))
    except ET.ParseError:
        raise SyncError('YouTube returned an unreadable feed.')
    except (KeyError, ValueError):
        raise SyncError('YouTube refused the API request; check YOUTUBE_API_KEY.')
    existing = {v.video_id: v for v in TestimonialVideo.objects.filter(platform='youtube')}
    added = 0
    for it in items:
        if not it['id']:
            continue
        guess = match_problem(f"{it['tags']} {it['title']} {it['caption']}")
        old = existing.get(it['id'])
        if old:                                              # staff edits win: only blanks are filled
            fill = {}
            if not old.description and it['caption']:
                fill['description'] = it['caption']
            if not old.tags and it['tags']:
                fill['tags'] = it['tags']
            if not old.problem_id and guess:
                fill['problem'] = guess
            if fill:
                TestimonialVideo.objects.filter(pk=old.pk).update(**fill)
            continue
        url = f"https://www.youtube.com/shorts/{it['id']}" if _is_short(it) else it['url']
        v = TestimonialVideo(title=it['title'][:200] or 'Video', description=it['caption'], url=url, is_published=True,
                             tags=it['tags'], problem=guess)
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
