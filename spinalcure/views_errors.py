"""Error pages. 404/410 use the public layout (with navigation back into the site); 500 is self-contained so it
renders even when the database or a context processor is what failed."""
from django.shortcuts import render
from django.template import loader
from django.http import HttpResponseServerError


def page_not_found(request, exception=None):
    return render(request, 'errors/404.html', status=404)


def gone(request):
    """Content that existed and was deliberately removed (unpublished article, retired practitioner)."""
    return render(request, 'errors/404.html', {'gone': True}, status=410)


def server_error(request):
    return HttpResponseServerError(loader.get_template('errors/500.html').render())
