"""Content translation rules: machine never overwrites a person's text; source change marks it stale."""
import pytest
from django.utils import translation

from clinic import content_i18n as ci
from clinic.models import ProblemCategory


class Stub:
    id = 'stub'

    def translate(self, items, to, names):
        return {k: f'[{to}] {t}' for k, t, _n in items}


@pytest.mark.django_db
def test_translation_rules():
    p = ProblemCategory.objects.create(name='Back Pain')
    lbl, oid = 'clinic.problemcategory', str(p.pk)
    units = lambda: [u for u in ci.iter_units('ta', [lbl]) if u.object_id == oid]

    assert units()[0].status == 'missing'
    done, errors, _ = ci.translate_units('ta', units(), provider=Stub())
    assert (done, errors) == (1, []) and units()[0].status == 'auto'

    ci.save_edit(lbl, oid, 'name', 'ta', 'முதுகு வலி', 'tester')           # a person edits
    ci.translate_units('ta', provider=Stub())                                 # machine run must not touch it
    assert units()[0].value == 'முதுகு வலி' and units()[0].status == 'edited'
    with translation.override('ta'):
        assert ci.tx(p, 'name') == 'முதுகு வலி'
    with translation.override('hi'):
        assert ci.tx(p, 'name') == 'Back Pain'                                # no translation: English fallback

    p.name = 'Lower Back Pain'; p.save()
    assert units()[0].status == 'stale'                                       # English changed
    ci.translate_units('ta', provider=Stub())
    assert units()[0].value == 'முதுகு வலி'                                  # a person's stale text is still protected
    ci.keep_mine(lbl, oid, 'name', 'ta'); assert units()[0].status == 'edited'
    ci.translate_units('ta', units(), force=True, provider=Stub())            # explicit Regenerate may overwrite
    assert units()[0].value == '[ta] Lower Back Pain'


def test_translated_html_is_sanitised():
    from clinic.templatetags.content_i18n import _sanitize
    out = _sanitize('Hi <span class="text-green-600">x</span><br><img src=x onerror=alert(1)><script>1</script>')
    assert '<span class="text-green-600">x</span><br>' in out and '<img' not in out and '<script' not in out
