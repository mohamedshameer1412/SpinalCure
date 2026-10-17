from django import template
from spinalcure.utils import encode_b64uuid

register = template.Library()

@register.filter(name='b64uuid')
def b64uuid_filter(value):
    """
    Encodes a UUID into a base64 url-safe string.
    """
    if not value:
        return ''
    encoded = encode_b64uuid(value)
    return encoded if encoded else str(value)

@register.filter(name='index')
def index(indexable, i):
    """Returns the item at the given index."""
    try:
        return indexable[i]
    except (IndexError, TypeError, KeyError):
        return ""
