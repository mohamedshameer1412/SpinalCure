import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import translation

User = get_user_model()


@pytest.mark.parametrize('lang,expected', [('ta', 'பங்கேற்பாளர்'), ('hi', 'प्रतिभागी'), ('ar', 'المشارك')])
def test_catalogue_lookup(lang, expected):
    with translation.override(lang):
        assert translation.gettext('Participant') == expected


@pytest.mark.parametrize('lang,rtl', [('en', False), ('ta', False), ('hi', False), ('te', False), ('ml', False), ('kn', False)])
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


@pytest.mark.parametrize('lang', ['ta', 'hi', 'te', 'ml', 'kn'])
def test_catalogue_is_complete_and_compiled_mo_is_current(lang):
    """Every extracted string has a translation, and the committed .mo (what production loads, since there is
    no msgfmt there) contains all of them."""
    from pathlib import Path
    import polib
    root = Path(__file__).resolve().parents[2] / 'locale' / lang / 'LC_MESSAGES'
    po = polib.pofile(str(root / 'django.po'))
    mo = polib.mofile(str(root / 'django.mo'))
    live = [e for e in po if not e.obsolete]
    missing = [e.msgid for e in live if not (e.msgstr or any(e.msgstr_plural.values()))]
    assert not missing, missing[:10]
    compiled = {e.msgid for e in mo}
    stale = [e.msgid for e in live if e.msgid not in compiled]
    assert not stale, f'run scripts/i18n_compile.py ({len(stale)} strings missing from .mo)'


def test_language_labels_are_native_script_whatever_the_django_version():
    from django.utils.translation import get_language_info
    from spinalcure.languages import NATIVE_CHOICES
    assert dict(NATIVE_CHOICES)['kn'] == 'ಕನ್ನಡ' and get_language_info('kn')['name_local'] == 'ಕನ್ನಡ'
    assert [c for c, _ in NATIVE_CHOICES] == ['en', 'ta', 'hi', 'te', 'ml', 'kn']
