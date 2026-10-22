import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

from clinic.content_i18n import REGISTRY, get_provider, object_coverage, tx

register = template.Library()


@register.filter(name='tx')
def tx_filter(obj, field):
    """{{ obj|tx:"field" }}: the field in the visitor's language, falling back to English."""
    return tx(obj, field) if obj is not None else ''


_ALLOWED = re.compile(r'&lt;(/?)(br|em|strong)\s*/?&gt;|&lt;span class=&quot;([\w\- ]{1,80})&quot;&gt;|&lt;/span&gt;')


def _sanitize(text):
    """Escape everything, then re-allow only <br>, <em>, <strong> and <span class="...">: no attributes that can run script."""
    def back(m):
        if m.group(2):
            return f'<{m.group(1)}{m.group(2)}>'
        if m.group(3) is not None:
            return f'<span class="{m.group(3)}">'
        return '</span>'
    return mark_safe(_ALLOWED.sub(back, escape(text)))


@register.filter
def sentence_lines(value):
    """"No Surgery. No Medicine. No Diet." -> one sentence per line (escaped, <br> between)."""
    import re
    from django.utils.html import conditional_escape
    from django.utils.safestring import mark_safe
    parts = [p for p in re.split(r'(?<=[.!?])\s+', str(value or '').strip()) if p]
    return mark_safe('<br>'.join(conditional_escape(p) for p in parts))


@register.filter(name='tx_html')
def tx_html_filter(obj, field):
    """Like tx, for fields that may hold simple markup (coloured heading spans). Translated text is sanitised;
    the English source keeps the existing behaviour (admin-authored, trusted)."""
    value = tx_filter(obj, field)
    return mark_safe(value) if value == getattr(obj, field, None) else _sanitize(value)


@register.inclusion_tag('clinic/partials/translation_panel.html', takes_context=True)
def translation_panel(context, obj, title=''):
    """Language tabs with % complete, editable translations and auto-translate for one saved record."""
    if obj is None or not getattr(obj, 'pk', None) or obj._meta.label_lower not in REGISTRY:
        return {'obj': None}
    request = context.get('request')
    provider = get_provider()
    uid = f"tr-{obj._meta.label_lower.replace('.', '-')}-{obj.pk}"
    return {'obj': obj, 'label': obj._meta.label_lower, 'langs': object_coverage(obj), 'uid': uid, 'title': title,
            'provider': provider.id if provider else None, 'csrf_token': context.get('csrf_token'),
            'next': (request.get_full_path() if request else '') + '#' + uid}


@register.filter(name='lines')
def lines_filter(text):
    """Non-empty lines of a text block, for bullet lists stored one item per line."""
    return [line.strip() for line in str(text or '').splitlines() if line.strip()]
