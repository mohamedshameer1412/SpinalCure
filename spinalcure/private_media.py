"""Private uploads (patient photos, staff photos, expense receipts): stored outside the web server's public folder
and served only to signed-in staff whose role may see them. Public website images stay in MEDIA_ROOT.
"""
import mimetypes
import posixpath

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.http import FileResponse, Http404
from django.utils.deconstruct import deconstructible
from django.utils.functional import cached_property

from .rbac import has_capability

# top-level folder -> capability needed to open files in it ('' = any signed-in staff member)
ACCESS = {'patients': 'patients.view', 'expenses': 'expenses.manage', 'users': ''}


@deconstructible
class PrivateStorage(FileSystemStorage):
    """FileSystemStorage rooted at PRIVATE_MEDIA_ROOT, with URLs that go through `serve` below."""

    @cached_property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @cached_property
    def base_url(self):
        return '/private-media/'


private_storage = PrivateStorage()


def get_private_storage():
    return private_storage


def serve(request, path):
    path = posixpath.normpath(path).lstrip('/')
    folder = path.split('/', 1)[0]
    if path.startswith('..') or folder not in ACCESS:
        raise Http404
    user = request.user
    if not (user.is_authenticated and user.is_active):
        raise Http404                                   # never reveal that a private file exists
    capability = ACCESS[folder]
    if capability and not has_capability(user, capability):
        raise Http404
    if not private_storage.exists(path):
        raise Http404
    resp = FileResponse(private_storage.open(path, 'rb'), content_type=mimetypes.guess_type(path)[0] or 'application/octet-stream')
    resp['Cache-Control'] = 'private, max-age=3600'
    resp['X-Content-Type-Options'] = 'nosniff'
    resp['Content-Security-Policy'] = "default-src 'none'"
    return resp


def move_into_private(folder):
    """Migration helper: move files already uploaded to MEDIA_ROOT/<folder> into PRIVATE_MEDIA_ROOT/<folder>.
    The stored names stay the same, so database rows need no change."""
    import shutil
    from pathlib import Path

    def forwards(apps, schema_editor):
        src, dst = Path(settings.MEDIA_ROOT) / folder, Path(settings.PRIVATE_MEDIA_ROOT) / folder
        if not src.is_dir() or src.resolve() == dst.resolve():
            return
        for f in src.rglob('*'):
            if f.is_file():
                target = dst / f.relative_to(src)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.move(str(f), str(target))
    return forwards
