"""Upload paths for private files (patient/staff photos, receipts): random names, so a file under /media/ cannot be
found by guessing its original filename. The extension is kept so the web server sends the right content type."""
import os
import uuid

from django.utils.deconstruct import deconstructible


@deconstructible
class RandomName:
    def __init__(self, folder):
        self.folder = folder

    def __call__(self, instance, filename):
        ext = os.path.splitext(filename)[1].lower()[:10]
        return f'{self.folder}/{uuid.uuid4().hex}{ext}'

    def __eq__(self, other):
        return isinstance(other, RandomName) and other.folder == self.folder


MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
IMAGE_EXT = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp', 'GIF': '.gif'}


class UploadRejected(ValueError):
    pass


def checked_image(upload):
    """Return the upload if Pillow can read it as a JPEG/PNG/WebP/GIF within the size limits, renamed to a random
    name with the extension of its real format. A file that only claims to be an image (or a valid image with
    something else appended, saved as .html/.svg) is never stored under a name the web server would execute or
    render as a page. Raises UploadRejected with a user-facing message."""
    from django.utils.translation import gettext
    from PIL import Image
    if upload is None:
        return None
    if upload.size > MAX_IMAGE_BYTES:
        raise UploadRejected(gettext('Image is larger than 8 MB.'))
    try:
        upload.seek(0)
        with Image.open(upload) as img:
            fmt = img.format
            img.verify()
        upload.seek(0)
        with Image.open(upload) as img:
            if img.width * img.height > MAX_IMAGE_PIXELS:
                raise UploadRejected(gettext('Image dimensions are too large.'))
    except UploadRejected:
        raise
    except Exception:
        raise UploadRejected(gettext('This file is not a valid image.'))
    if fmt not in IMAGE_EXT:
        raise UploadRejected(gettext('Use a JPEG, PNG or WebP image.'))
    upload.seek(0)
    upload.name = f'{uuid.uuid4().hex}{IMAGE_EXT[fmt]}'
    return upload


def reject_bad_uploads(view):
    """View decorator: a rejected image upload becomes a form error message instead of a server error."""
    from functools import wraps

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except UploadRejected as e:
            from django.contrib import messages
            from django.shortcuts import redirect
            messages.error(request, str(e))
            return redirect(request.get_full_path())
    return wrapper
