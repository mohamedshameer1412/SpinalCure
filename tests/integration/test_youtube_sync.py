"""Channel feed import: new uploads (videos and Shorts) become stories; existing ones are never touched."""
import pytest

from clinic import youtube_sync
from clinic.models import ClinicProfile, TestimonialVideo

pytestmark = pytest.mark.django_db

FEED = '''<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015"
 xmlns:media="http://search.yahoo.com/mrss/">
<entry><yt:videoId>AAAAAAAAAAA</yt:videoId><title>A Short</title><link rel="alternate" href="https://www.youtube.com/shorts/AAAAAAAAAAA"/>
<published>2025-11-17T08:22:37+00:00</published><media:group><media:description>Caption one

Hours: 10am</media:description></media:group></entry>
<entry><yt:videoId>BBBBBBBBBBB</yt:videoId><title>A Video</title><link rel="alternate" href="https://www.youtube.com/watch?v=BBBBBBBBBBB"/>
<published>2025-11-10T08:00:00+00:00</published><media:group><media:description>Caption two</media:description></media:group></entry>
</feed>'''


@pytest.fixture
def clinic(monkeypatch, settings):
    settings.YOUTUBE_API_KEY = ''
    c = ClinicProfile.objects.create(name='C', address='a', phone='9876543210', email='c@x.com',
                                     youtube='https://www.youtube.com/channel/UC' + 'a' * 22)
    monkeypatch.setattr(youtube_sync, '_get', lambda url: FEED)
    monkeypatch.setattr(youtube_sync.stories, 'import_frame', lambda *a, **k: (_ for _ in ()).throw(ValueError()))
    return c


def test_sync_adds_new_videos_with_title_and_caption_once(clinic):
    assert youtube_sync.sync(clinic) == (2, 0)
    short = TestimonialVideo.objects.get(video_id='AAAAAAAAAAA')
    assert short.title == 'A Short' and short.description == 'Caption one' and short.is_short and short.is_published
    assert TestimonialVideo.objects.get(video_id='BBBBBBBBBBB').is_short is False
    assert youtube_sync.sync(clinic) == (0, 2)                       # second run adds nothing
    assert TestimonialVideo.objects.count() == 2


def test_sync_keeps_staff_edits(clinic):
    youtube_sync.sync(clinic)
    TestimonialVideo.objects.filter(video_id='AAAAAAAAAAA').update(title='Edited', is_published=False)
    youtube_sync.sync(clinic)
    v = TestimonialVideo.objects.get(video_id='AAAAAAAAAAA')
    assert v.title == 'Edited' and not v.is_published


def test_channel_link_is_required(clinic):
    clinic.youtube = ''
    with pytest.raises(youtube_sync.SyncError):
        youtube_sync.sync(clinic)


def test_api_path_imports_everything_with_tags_and_sorts_into_a_problem(clinic, settings, monkeypatch):
    from clinic.models import ProblemCategory
    ProblemCategory.objects.create(name='Back Pain', keywords='lumbar')
    settings.YOUTUBE_API_KEY = 'k'
    monkeypatch.setattr(youtube_sync, '_api_entries', lambda cid: iter([
        {'id': 'CCCCCCCCCCC', 'title': 'Relief', 'url': 'https://www.youtube.com/watch?v=CCCCCCCCCCC', 'caption': 'c',
         'published': '2025-01-01T00:00:00+00:00', 'tags': 'acupuncture, lumbar pain', 'duration': 'PT12M'}]))
    assert youtube_sync.sync(clinic) == (1, 0)
    v = TestimonialVideo.objects.get(video_id='CCCCCCCCCCC')
    assert v.tags == 'acupuncture, lumbar pain' and v.problem.name == 'Back Pain' and not v.is_short
    # an existing video with blanks gets them filled, never overwritten
    TestimonialVideo.objects.filter(pk=v.pk).update(tags='', description='mine')
    youtube_sync.sync(clinic)
    v.refresh_from_db()
    assert v.tags and v.description == 'mine'
