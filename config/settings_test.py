"""Pytest settings: the running app, without the profiler tax.

``config.settings`` loads Silk whenever ``DEBUG`` is on. Silk wraps every
SQL compiler with ``EXPLAIN`` and writes profiling rows, which is useful on
a live server and the reason a request-heavy suite crawls. Tests also skip
PBKDF2 and talk to an in-process cache so they are not bound by Redis or
password hashing.
"""

from config.settings import *  # noqa: F403

INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "silk"]
MIDDLEWARE = [mw for mw in MIDDLEWARE if not mw.startswith("silk.")]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "KEY_PREFIX": "onest",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
