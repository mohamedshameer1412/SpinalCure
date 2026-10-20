"""{% jsonld data %}: schema.org JSON-LD, escaped like json_script so stored text can never close the script tag."""
import json

from django import template
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.safestring import mark_safe

from spinalcure import seo

register = template.Library()
_ESCAPES = {ord('>'): '\\u003E', ord('<'): '\\u003C', ord('&'): '\\u0026'}


@register.simple_tag
def jsonld(data):
    if not data:
        return ''
    text = json.dumps(data, cls=DjangoJSONEncoder, ensure_ascii=False).translate(_ESCAPES)
    return mark_safe(f'<script type="application/ld+json">{text}</script>')


@register.simple_tag
def ld(kind, *args):
    """{% ld "event" event %} -> JSON-LD built by spinalcure.seo.<kind>_ld."""
    return jsonld(getattr(seo, f'{kind}_ld')(*args))


@register.simple_tag
def ld_breadcrumbs(*pairs):
    """{% ld_breadcrumbs "Home" home_url "Blog" blog_url post.title request.path %}"""
    return jsonld(seo.breadcrumbs_ld(*zip(pairs[::2], pairs[1::2])))
