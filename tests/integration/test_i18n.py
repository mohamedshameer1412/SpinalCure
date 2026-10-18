import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import translation

User = get_user_model()


@pytest.mark.parametrize('lang,expected', [('ta', 'பங்கேற்பாளர்'), ('hi', 'प्रतिभागी'), ('ar', 'المشارك')])
def test_catalogue_lookup(lang, expected):
    with translation.override(lang):
        assert translation.gettext('Participant') == expected


@pytest.mark.parametrize('lang,rtl', [('en', False), ('ta', False), ('hi', False), ('ar', True)])
@pytest.mark.django_db
def test_public_page_lang_and_dir(lang, rtl):
    r = Client().get(f'/{lang}/clinic/events/')
    assert r.status_code == 200
    html = r.content.decode()
    assert f'lang="{lang}"' in html
    assert ('dir="rtl"' in html) == rtl


@pytest.mark.django_db
def test_set_language_persists_on_user():
    u = User.objects.create_user(username='lang', email='lang@example.com', password='x-Str0ng-pass!', role='doctor')
    c = Client()
    c.force_login(u)
    r = c.post('/i18n/setlang/', {'language': 'ta', 'next': '/en/events/'})
    assert r.status_code == 302
    u.refresh_from_db()
    assert u.language == 'ta'
    assert r['Location'].startswith('/ta/')


@pytest.mark.django_db
def test_set_language_rejects_unknown_code():
    u = User.objects.create_user(username='lang2', email='lang2@example.com', password='x-Str0ng-pass!', role='doctor', language='en')
    c = Client()
    c.force_login(u)
    c.post('/i18n/setlang/', {'language': 'xx', 'next': '/en/'})
    u.refresh_from_db()
    assert u.language == 'en'
