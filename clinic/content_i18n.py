"""Website content translation: registry of translatable fields, per-language coverage, edit rules and
machine-translation providers. English is the source (it lives on the models); other languages live in
clinic.Translation. Rules (same as the Swagatam invitation builder):

  * A person's words (edited / final) are never overwritten by a machine, unless staff press "Regenerate".
  * Machine output (auto) can be refreshed freely.
  * If the English source changes, translations made from the old text show as "stale" until reviewed.
"""
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.utils.translation import get_language, gettext

from .models import Translation

SOURCE_LANG = 'en'

# model label -> translatable fields. Add a model/field here and it appears in Admin > Translations.
REGISTRY = {
    'clinic.clinicprofile': ['name', 'tagline', 'about', 'hero_title', 'hero_subtitle', 'about_label', 'about_title',
                             'about_quote', 'services_label', 'services_title', 'services_description', 'team_label',
                             'team_title', 'team_description', 'testimonials_label', 'testimonials_title',
                             'working_hours', 'address', 'footer_text'],
    'clinic.clinicservice': ['title', 'description'],
    'clinic.practitioner': ['name', 'title', 'designation_tag', 'specialization', 'qualifications', 'bio'],
    'clinic.problemcategory': ['name'],
    'clinic.clinictestimonial': ['patient_name', 'patient_designation', 'review_text', 'owner_reply', 'posted_label'],
    'clinic.testimonialvideo': ['title', 'patient_name', 'description'],
    'clinic.blogpost': ['title', 'excerpt', 'content', 'meta_description'],
    'clinic.blogtag': ['name'],
    'events.event': ['title', 'description', 'venue', 'presenter', 'access_instructions'],
    'courses.course': ['title', 'short_description', 'description', 'outcomes', 'course_content', 'duration'],
    'courses.coursebatch': ['name', 'schedule_details'],
}
# Person / place names: transliterated, not translated.
NAME_FIELDS = {'name', 'patient_name', 'presenter', 'venue'}
LABELS = {
    'clinic.clinicprofile': 'Clinic', 'clinic.clinicservice': 'Services', 'clinic.practitioner': 'Specialists',
    'clinic.problemcategory': 'Problems', 'clinic.clinictestimonial': 'Testimonials', 'clinic.testimonialvideo': 'Reels & Shorts',
    'clinic.blogpost': 'Blog posts', 'clinic.blogtag': 'Blog tags', 'events.event': 'Events', 'courses.course': 'Courses',
    'courses.coursebatch': 'Course batches',
}


def target_langs():
    return [c for c, _ in settings.LANGUAGES if c != SOURCE_LANG]


def source_hash(text):
    return hashlib.sha1((text or '').strip().encode('utf-8')).hexdigest()[:16]


def is_manual(entry):
    return bool(entry) and entry.method == 'manual'


# ── Read side (public site) ─────────────────────────────────────────────────────────────────────

def _table(lang):
    key = f'content_tr_{lang}'
    table = cache.get(key)
    if table is None:
        table = {(r.model_label, r.object_id, r.field): r.value
                 for r in Translation.objects.filter(lang=lang).exclude(value='')}
        cache.set(key, table, 60)  # ponytail: per-process cache; a Redis cache backend makes invalidation instant across workers
    return table


def tx(obj, field, lang=None):
    """Text of obj.field in the active language, falling back to the English source."""
    if isinstance(obj, dict):
        return obj.get(field, '')
    src = getattr(obj, field, '') or ''
    lang = (lang or get_language() or SOURCE_LANG).split('-')[0]
    if lang == SOURCE_LANG or not src or not hasattr(obj, '_meta'):
        return src
    return _table(lang).get((obj._meta.label_lower, str(obj.pk), field)) or src


# ── Units & coverage ────────────────────────────────────────────────────────────────────────────

@dataclass
class Unit:
    model_label: str
    object_id: str
    field: str
    obj_name: str
    source: str
    entry: object  # Translation | None
    status: str    # missing | stale | auto | edited | final
    is_name: bool

    @property
    def label(self):
        return self.field.replace('_', ' ')

    @property
    def key(self):
        return f'{self.model_label}|{self.object_id}|{self.field}'

    @property
    def value(self):
        return self.entry.value if self.entry else ''

    @property
    def machine_may_write(self):
        e = self.entry
        if self.status in ('missing', 'auto'):
            return True
        if self.status == 'stale':
            return not is_manual(e)
        return False


def _status(e, src):
    if not e or not e.value.strip():
        return 'missing'
    return 'stale' if e.source_hash != source_hash(src) else e.status


def object_units(obj, lang):
    """Units of a single record in one language (for the panel inside each content form)."""
    label = obj._meta.label_lower
    entries = {t.field: t for t in Translation.objects.filter(model_label=label, object_id=str(obj.pk), lang=lang)}
    out = []
    for f in REGISTRY.get(label, []):
        src = str(getattr(obj, f, '') or '')
        if src.strip():
            u = Unit(label, str(obj.pk), f, str(obj)[:80], src, entries.get(f), _status(entries.get(f), src), f in NAME_FIELDS)
            u.lang = lang
            out.append(u)
    return out


def object_coverage(obj):
    names = dict(settings.LANGUAGES)
    out = []
    for lang in target_langs():
        units = object_units(obj, lang)
        done = sum(1 for u in units if u.status != 'missing')
        out.append({'lang': lang, 'name': names[lang], 'units': units, 'total': len(units), 'done': done,
                    'pct': round(100 * done / len(units)) if units else 100,
                    'todo': sum(1 for u in units if u.status in ('missing', 'stale'))})
    return out


def iter_units(lang, models=None):
    entries = {(t.model_label, t.object_id, t.field): t for t in Translation.objects.filter(lang=lang)}
    for label, fields in REGISTRY.items():
        if models and label not in models:
            continue
        for obj in apps.get_model(label).objects.all():
            for f in fields:
                src = getattr(obj, f, '') or ''
                if not str(src).strip():
                    continue
                e = entries.get((label, str(obj.pk), f))
                yield Unit(label, str(obj.pk), f, str(obj)[:80], str(src), e, _status(e, src), f in NAME_FIELDS)


def coverage():
    """[{lang, name, total, done, pct, missing, stale, auto, edited, final}] for each target language."""
    names = dict(settings.LANGUAGES)
    out = []
    for lang in target_langs():
        c = {'missing': 0, 'stale': 0, 'auto': 0, 'edited': 0, 'final': 0}
        for u in iter_units(lang):
            c[u.status] += 1
        total = sum(c.values())
        out.append({'lang': lang, 'name': names[lang], 'total': total, 'done': total - c['missing'],
                    'pct': round(100 * (total - c['missing']) / total) if total else 100,
                    'reviewed_pct': round(100 * (c['edited'] + c['final']) / total) if total else 100, **c})
    return out


# ── Edit rules ──────────────────────────────────────────────────────────────────────────────────

def _source_of(label, oid, field):
    obj = apps.get_model(label).objects.filter(pk=oid).first()
    return (getattr(obj, field, '') or '') if obj else ''


def save_edit(label, oid, field, lang, text, user=''):
    """A person typed this. Blank removes the translation (falls back to English)."""
    if label not in REGISTRY or field not in REGISTRY[label] or lang not in target_langs():
        raise ValueError('Not a translatable field')
    if not text.strip():
        Translation.objects.filter(model_label=label, object_id=oid, field=field, lang=lang).delete()
        return
    Translation.objects.update_or_create(
        model_label=label, object_id=oid, field=field, lang=lang,
        defaults=dict(value=text, status='edited', method='manual', updated_by=str(user)[:150],
                      source_hash=source_hash(_source_of(label, oid, field))))


def mark_final(label, oid, field, lang, user=''):
    t = Translation.objects.filter(model_label=label, object_id=oid, field=field, lang=lang).first()
    if t:
        t.status, t.updated_by = 'final', str(user)[:150]
        t.source_hash = source_hash(_source_of(label, oid, field))
        t.save()


def keep_mine(label, oid, field, lang, user=''):
    """Stale translation still fits the new English: re-pin it to the current source."""
    t = Translation.objects.filter(model_label=label, object_id=oid, field=field, lang=lang).first()
    if t:
        t.status = 'edited' if is_manual(t) else 'auto'
        t.source_hash, t.updated_by = source_hash(_source_of(label, oid, field)), str(user)[:150]
        t.save()


def _store_machine(u, text, provider_id, user=''):
    Translation.objects.update_or_create(
        model_label=u.model_label, object_id=u.object_id, field=u.field, lang=u.lang,
        defaults=dict(value=text, status='auto', method=f'machine:{provider_id}', source_hash=source_hash(u.source),
                      updated_by=str(user)[:150]))


# ── Providers ───────────────────────────────────────────────────────────────────────────────────

LANG_NAMES = {'en': 'English', 'ta': 'Tamil', 'hi': 'Hindi', 'te': 'Telugu', 'ml': 'Malayalam', 'kn': 'Kannada'}


def _http_json(url, payload=None, headers=None, timeout=60):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={'content-type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Translation service error {e.code}' + (' (quota)' if e.code == 429 else f': {e.read().decode()[:200]}')) from None
    except urllib.error.URLError as e:
        raise RuntimeError(f'Translation service unreachable: {e.reason}') from None


class AnthropicProvider:
    """LLM: best for names (transliterates), honorifics and the clinic's medical register."""
    id = 'anthropic'

    def translate(self, items, to, names):
        prompt = '\n'.join([
            f'Translate the values of this JSON object from English to {LANG_NAMES.get(to, to)}.',
            'They are website texts of an acupuncture and spine-care clinic in Chennai, India.',
            'Rules:',
            '- Natural, warm, professional register used by clinics in that language; medical terms stay accurate.',
            f'- These keys hold person, place or brand names: TRANSLITERATE into the target script, never translate meaning: {[k for k, _t, n in items if n]}' if any(n for _k, _t, n in items) else '',
            f'- These names inside other texts must be transliterated, not translated: {"; ".join(names)}' if names else '',
            '- Keep HTML tags, line breaks, numbers, phone numbers, URLs, emoji and punctuation style. Do not add or remove information.',
            'Return ONLY a JSON object with exactly the same keys.', '',
            json.dumps({k: t for k, t, _n in items}, ensure_ascii=False, indent=1)])
        body = _http_json('https://api.anthropic.com/v1/messages', {
            'model': settings.ANTHROPIC_MODEL, 'max_tokens': 8000, 'messages': [{'role': 'user', 'content': prompt}]},
            {'x-api-key': settings.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01'}, timeout=120)
        text = ''.join(c.get('text', '') for c in body.get('content', []) if c.get('type') == 'text')
        m = re.search(r'\{.*\}', text, re.S)
        out = json.loads(m.group(0)) if m else {}
        return {k: str(v) for k, v in out.items() if k in {i[0] for i in items} and str(v).strip()}


class GoogleProvider:
    id = 'google'

    def translate(self, items, to, names):
        def protect(s):
            s = s.replace('&', '&amp;').replace('<', '&lt;') if '<' not in s else s
            for n in names:
                s = s.replace(n, f'<span translate="no">{n}</span>')
            return s
        body = _http_json(f'https://translation.googleapis.com/language/translate/v2?key={urllib.parse.quote(settings.GOOGLE_TRANSLATE_API_KEY)}',
                          {'q': [protect(t) for _k, t, _n in items], 'source': SOURCE_LANG, 'target': to, 'format': 'html'})
        import html
        res = body['data']['translations']
        return {k: html.unescape(re.sub(r'</?span[^>]*>', '', res[i]['translatedText'])) for i, (k, _t, _n) in enumerate(items)}


class MyMemoryProvider:
    """Free, no key. Basic quality, ~5,000 chars/day per IP (50,000 with MYMEMORY_EMAIL). Names are not transliterated well."""
    id = 'mymemory'

    def _one(self, text, to):
        url = f'https://api.mymemory.translated.net/get?q={urllib.parse.quote(text)}&langpair={SOURCE_LANG}|{to}'
        if settings.MYMEMORY_EMAIL:
            url += f'&de={urllib.parse.quote(settings.MYMEMORY_EMAIL)}'
        body = _http_json(url)
        t = (body.get('responseData') or {}).get('translatedText', '')
        if t.startswith('MYMEMORY WARNING'):
            raise RuntimeError('The free translation quota is used up for today. Add ANTHROPIC_API_KEY or GOOGLE_TRANSLATE_API_KEY.')
        if int(body.get('responseStatus', 200)) != 200:
            raise RuntimeError(body.get('responseDetails') or 'Free translation service error')
        return t

    def translate(self, items, to, names):
        out = {}
        for k, text, _n in items:
            # the API takes ~480 chars per call: translate paragraph by paragraph / sentence by sentence
            chunks = [c for c in re.split(r'(?<=[.!?])\s+|\n+', text) if c.strip()]
            parts, buf = [], ''
            for c in chunks:
                if len(buf) + len(c) > 450 and buf:
                    parts.append(buf)
                    buf = ''
                buf = f'{buf} {c}'.strip()
            parts.append(buf)
            out[k] = ' '.join(self._one(p[:480], to) for p in parts if p)
        return out


def get_provider():
    if settings.ANTHROPIC_API_KEY:
        return AnthropicProvider()
    if settings.GOOGLE_TRANSLATE_API_KEY:
        return GoogleProvider()
    if settings.TRANSLATION_FREE:
        return MyMemoryProvider()
    return None


# ── Machine translation ─────────────────────────────────────────────────────────────────────────

def translate_units(lang, units=None, force=False, user='', provider=None):
    """Fill every unit a machine may write. `force` (Regenerate) also overwrites a person's text for the given units.
    Returns (translated_count, [errors], provider_id|None)."""
    provider = provider or get_provider()
    if not provider:
        return 0, [], None
    units = list(iter_units(lang) if units is None else units)
    for u in units:
        u.lang = lang
    pending = [u for u in units if force or u.machine_may_write]
    names = sorted({str(getattr(apps.get_model(l).objects.filter(pk=o).first(), 'name', '') or '')
                    for l, o in {(u.model_label, u.object_id) for u in pending if u.model_label in ('clinic.clinicprofile', 'clinic.practitioner')}} - {''})
    done, errors = 0, []
    for i in range(0, len(pending), 25):
        batch = pending[i:i + 25]
        try:
            out = provider.translate([(u.key, u.source, u.is_name) for u in batch], lang, names)
        except Exception as e:  # keep going with the other batches; report at the end
            msg = str(e)
            if '429' in msg or 'quota' in msg.lower() or 'MYMEMORY WARNING' in msg:
                # the daily limit will not reset mid-run: stop instead of failing every remaining batch
                errors.append(f'{LANG_NAMES.get(lang, lang)}: ' + gettext(
                    'The free translation service has reached its daily limit. Translations saved so far are kept; '
                    'try again tomorrow, or add ANTHROPIC_API_KEY or GOOGLE_TRANSLATE_API_KEY for unlimited use.'))
                break
            errors.append(f'{LANG_NAMES.get(lang, lang)}: {msg[:160]}')
            continue
        for u in batch:
            if out.get(u.key, '').strip():
                _store_machine(u, out[u.key], provider.id, user)
                done += 1
    return done, errors, provider.id
