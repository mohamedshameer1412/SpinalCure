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
