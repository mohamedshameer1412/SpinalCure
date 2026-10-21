"""Lossless compression of generated downloads (CSV, text, JSON, calendar files, Excel).

* DownloadGzipMiddleware: gzips attachment responses whose body is plain text, when the browser says it accepts gzip.
  Only downloads are touched, never HTML pages, so it does not expose page secrets to compression side channels.
* recompress_zip: rewrites a .xlsx (a zip file) at the maximum deflate level; the contents are byte-identical.
"""
import gzip
import io
import re
import zipfile

from django.utils.cache import patch_vary_headers

_TEXTUAL = re.compile(r'^(text/|application/(json|xml|csv))')
MIN_BYTES = 512


class DownloadGzipMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (response.streaming or response.has_header('Content-Encoding') or len(response.content) < MIN_BYTES
                or 'attachment' not in response.get('Content-Disposition', '')
                or not _TEXTUAL.match(response.get('Content-Type', ''))
                or 'gzip' not in request.META.get('HTTP_ACCEPT_ENCODING', '')):
            return response
        compressed = gzip.compress(response.content, compresslevel=9, mtime=0)
        if len(compressed) < len(response.content):
            response.content = compressed
            response['Content-Encoding'] = 'gzip'
            response['Content-Length'] = str(len(compressed))
            patch_vary_headers(response, ('Accept-Encoding',))
        return response


def recompress_zip(data):
    """The same zip with every member deflated at level 9 (the original is returned if that is not smaller)."""
    try:
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as dst:
            for info in src.infolist():
                dst.writestr(info, src.read(info), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        return out.getvalue() if len(out.getvalue()) < len(data) else data
    except Exception:
        return data
