from django.conf import settings
from django.views.i18n import set_language as django_set_language


def set_language(request):
    """Django's language switch, plus remembering the choice on the signed-in user's profile
    so notifications and emails are rendered in the same language."""
    response = django_set_language(request)
    code = request.POST.get('language')
    user = getattr(request, 'user', None)
    if (user is not None and user.is_authenticated and hasattr(user, 'language')
            and code in dict(settings.LANGUAGES) and user.language != code):
        user.language = code
        user.save(update_fields=['language'])
    return response
