from django import template

from spinalcure.rbac import has_capability

register = template.Library()


@register.filter(name='can')
def can(user, capability):
    """{% if request.user|can:'billing.view' %}"""
    return has_capability(user, capability)
