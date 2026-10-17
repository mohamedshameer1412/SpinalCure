from django.utils.functional import SimpleLazyObject

from .roles import perms_for


def role_perms(request):
    """`can.<perm>` in templates; lazy so public pages pay nothing."""
    return {'can': SimpleLazyObject(lambda: perms_for(request.user))}
