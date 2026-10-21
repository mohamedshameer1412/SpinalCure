"""
Django settings for SpinalCure project.
Environment-specific settings are imported based on DJANGO_ENV (default: production, so a deployment that
forgets to set it never runs with DEBUG on). Set DJANGO_ENV=development for local work.

When DJANGO_SETTINGS_MODULE names a submodule explicitly (e.g. spinalcure.settings.test) this package
must not pull in any environment, otherwise importing the submodule would load production settings first.
"""
import os

# Shared hosting (cPanel) has no compiler for mysqlclient: fall back to pure-Python PyMySQL under the same name.
# Django checks the driver version, so PyMySQL reports the mysqlclient release it is compatible with.
try:
    import MySQLdb  # noqa: F401
except ImportError:
    try:
        import pymysql
        pymysql.version_info = (2, 2, 1, 'final', 0)
        pymysql.install_as_MySQLdb()
    except ImportError:
        pass

if os.environ.get('DJANGO_SETTINGS_MODULE', 'spinalcure.settings') == 'spinalcure.settings':
    from .base import *

    _env = os.getenv('DJANGO_ENV', 'production').lower()

    if _env == 'production':
        from .production import *
    elif _env == 'staging':
        from .staging import *
    else:
        from .development import *
