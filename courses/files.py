"""Course material uploads: documents are checked by their real file header (not just the extension) and size."""
import os

from django.core.exceptions import ValidationError
from django.utils.translation import gettext

from spinalcure.uploads import UploadRejected, checked_video

DOC_EXTENSIONS = ('.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.csv', '.txt')
VIDEO_EXTENSIONS = ('.mp4', '.webm', '.mov')
MAX_DOC_BYTES = 25 * 1024 * 1024
_OLE = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'            # legacy .doc / .ppt / .xls
_ZIP = b'PK\x03\x04'                                    # .docx / .pptx / .xlsx


def validate_material(upload):
    """Accept PDF, Office documents, CSV/TXT and short videos; reject anything whose content does not match its name."""
    from django.core.files.uploadedfile import UploadedFile
    if not isinstance(upload, UploadedFile):
        return                                          # already stored
    ext = os.path.splitext(upload.name or '')[1].lower()
    if ext in VIDEO_EXTENSIONS:
        try:
            checked_video(upload)
        except UploadRejected as e:
            raise ValidationError(str(e))
        return
    if ext not in DOC_EXTENSIONS:
        raise ValidationError(gettext('Upload a PDF, Word, PowerPoint, Excel, CSV, text or video (MP4, WebM, MOV) file.'))
    if upload.size > MAX_DOC_BYTES:
        raise ValidationError(gettext('Documents can be at most 25 MB. For bigger files, paste a Drive link instead.'))
    upload.seek(0)
    head = upload.read(8)
    upload.seek(0)
    ok = {'.pdf': head[:4] == b'%PDF', '.doc': head == _OLE, '.ppt': head == _OLE, '.xls': head == _OLE,
          '.docx': head[:4] == _ZIP, '.pptx': head[:4] == _ZIP, '.xlsx': head[:4] == _ZIP}.get(ext)
    if ext in ('.csv', '.txt'):
        sample = upload.read(4096)
        upload.seek(0)
        ok = b'\x00' not in sample
    if not ok:
        raise ValidationError(gettext('This file does not look like a real %(ext)s document.') % {'ext': ext})


def kind_for(name):
    ext = os.path.splitext(name or '')[1].lower()
    return 'video' if ext in VIDEO_EXTENSIONS else 'pdf' if ext == '.pdf' else 'doc'
