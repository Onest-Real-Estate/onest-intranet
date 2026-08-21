"""Django settings for the Onest starter project."""

import logging
from pathlib import Path

from decouple import AutoConfig, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

# Reads environment variables first, then a .env file at the project root
# (see .env.example).
config = AutoConfig(search_path=BASE_DIR)

SECRET_KEY = config(
    "DJANGO_SECRET_KEY", default="django-insecure-dev-only-change-me-before-deploying"
)

DEBUG = config("DJANGO_DEBUG", default=True, cast=bool)

ALLOWED_HOSTS = config(
    "DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv()
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "django_vite",
    "inertia",
    "typescript_routes",
    # celery beat (periodic tasks stored in the database)
    "django_celery_beat",
    # allauth
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.microsoft",
    # Local
    "apps.user",
    "apps.web",
    "apps.audit",
]

# Silk (SQL profiling, N+1 detection) is dev-only: its web UI lives at
# /silk/. Kept out of INSTALLED_APPS in production so the package can stay
# in the dev dependency group only.
if DEBUG:
    INSTALLED_APPS += ["silk"]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "apps.audit.middleware.AuditContextMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.web.middleware.AuthorizationPolicyMiddleware",
    # New SSO users are sent through the /onboarding flow until their profile
    # is complete (apps/user/middleware.py). Runs after auth so request.user
    # is available, before Inertia so redirects pass through cleanly.
    "apps.user.middleware.ProfileCompletionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Inertia must run after the auth middleware; the share middleware runs
    # after Inertia so it can attach props to every Inertia page.
    "inertia.middleware.InertiaMiddleware",
    "apps.web.middleware.InertiaShareMiddleware",
]

# Silk must sit near the top of the middleware stack so it can profile the
# whole request (dev only).
if DEBUG:
    MIDDLEWARE.insert(0, "silk.middleware.SilkyMiddleware")

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Defaults to SQLite for zero-config local development; set DB_ENGINE/HOST etc.
# (e.g. via the compose files) to use PostgreSQL.
DATABASES = {
    "default": {
        "ENGINE": config("DB_ENGINE", default="django.db.backends.sqlite3"),
        "NAME": config("DB_NAME", default=str(BASE_DIR / "db.sqlite3")),
        "USER": config("DB_USER", default=""),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("DB_HOST", default=""),
        "PORT": config("DB_PORT", default="5432", cast=int),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",  # noqa: E501
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Custom email-based user (no username); see apps/user/models.py.
AUTH_USER_MODEL = "user.User"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Vite build output (frontend/ -> assets/ -> served by Django).
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "assets"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Local media (used when S3/MinIO is not configured).
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------------------
# Object storage (S3 / MinIO)
# ---------------------------------------------------------------------------
# Enable with USE_S3=1 and point the AWS_* vars at your MinIO endpoint. The
# bucket is made publicly readable by the compose minio-init service.
USE_S3 = config("USE_S3", default=False, cast=bool)
if USE_S3:
    AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default="")
    AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default="")
    AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="onest")
    # Endpoint used by boto3 for uploads — the compose-internal service URL
    # (e.g. http://minio:9000).
    AWS_S3_ENDPOINT_URL = config("AWS_S3_ENDPOINT_URL", default="")
    # Host browsers can reach, used to build public media URLs (scheme-less
    # "host:port"; the compose minio-init service sets the bucket to public read).
    AWS_S3_CUSTOM_DOMAIN = config("AWS_S3_CUSTOM_DOMAIN", default="")
    AWS_S3_URL_PROTOCOL = config("AWS_S3_URL_PROTOCOL", default="http:")
    AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="us-east-1")
    # Virtual-hosted style is what AWS S3 expects; MinIO-style endpoints need
    # "path" (set it via env, e.g. in the dev compose stack).
    AWS_S3_ADDRESSING_STYLE = config("AWS_S3_ADDRESSING_STYLE", default="virtual")
    # Public-read bucket: no presigned URLs needed.
    AWS_QUERYSTRING_AUTH = False
    DEFAULT_FILE_STORAGE_BACKEND = "storages.backends.s3boto3.S3Boto3Storage"
else:
    DEFAULT_FILE_STORAGE_BACKEND = "django.core.files.storage.FileSystemStorage"

# Static files are served by WhiteNoise in production (compressed + hashed via
# collectstatic); media files go to MinIO when USE_S3 is enabled.
STORAGES = {
    "default": {"BACKEND": DEFAULT_FILE_STORAGE_BACKEND},
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}

# ---------------------------------------------------------------------------
# Cache / sessions (Redis)
# ---------------------------------------------------------------------------
REDIS_URL = config("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
            "KEY_PREFIX": "onest",
        }
    }
    # Sessions live in Redis with a DB fallback.
    SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "KEY_PREFIX": "onest",
        }
    }
    SESSION_ENGINE = "django.contrib.sessions.backends.db"

# ---------------------------------------------------------------------------
# Celery (background tasks + beat scheduler)
# ---------------------------------------------------------------------------
# django-celery-beat stores periodic task schedules in the database (managed
# from Django admin); Redis is the broker and result backend. The compose
# stacks use dedicated Redis DBs so the broker/backend never compete with the
# cache (db 0).
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = config(
    "CELERY_RESULT_BACKEND", default="redis://localhost:6379/2"
)
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TIMEZONE = TIME_ZONE

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
# Everything logs to the console (captured by Docker/journald); the `apps`
# logger covers first-party code and is quieted from Django's own chatter.
# Sentry errors are attached via the logging integration below.
LOG_LEVEL = config("LOG_LEVEL", default="DEBUG" if DEBUG else "INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "apps": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
}

# ---------------------------------------------------------------------------
# Email (Mailpit in the compose stack; console backend for local dev)
# ---------------------------------------------------------------------------
# Django 6.1 replaces these EMAIL_* settings with a MAILERS dict (see
# docs.djangoproject.com/howto/mailers-migration). We're still on Django 6.0
# because django-ninja and django-celery-beat pin Django<6.1; once they
# support 6.1, replace this block with:
#
#   MAILERS = {
#       "default": {
#           "BACKEND": config(
#               "EMAIL_BACKEND",
#               default="django.core.mail.backends.console.EmailBackend",
#           ),
#           "OPTIONS": {
#               "host": config("EMAIL_HOST", default="localhost"),
#               "port": config("EMAIL_PORT", default=1025, cast=int),
#               "username": config("EMAIL_HOST_USER", default=""),
#               "password": config("EMAIL_HOST_PASSWORD", default=""),
#               "use_tls": config("EMAIL_USE_TLS", default=False, cast=bool),
#               "use_ssl": config("EMAIL_USE_SSL", default=False, cast=bool),
#           },
#       },
#   }
EMAIL_BACKEND = config(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = config("EMAIL_HOST", default="localhost")
EMAIL_PORT = config("EMAIL_PORT", default=1025, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=False, cast=bool)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="Onest <noreply@onest.local>")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# django-vite
# ---------------------------------------------------------------------------
# In dev mode Django loads assets from the Vite dev server (HMR); in production
# it reads the manifest generated by `pnpm run build` (see README).
DJANGO_VITE = {
    "default": {
        "dev_mode": DEBUG,
        "dev_server_protocol": "http",
        "dev_server_host": "localhost",
        "dev_server_port": 5173,
    }
}

# ---------------------------------------------------------------------------
# Inertia
# ---------------------------------------------------------------------------
INERTIA_LAYOUT = "layout.html"
# Bump whenever the frontend bundle changes so stale clients get a full reload.
INERTIA_VERSION = "13"

# Optional external help centre. The shell exposes it only when it is an
# absolute, credential-free HTTPS URL; an empty or unsafe value leaves the
# future-facing help entry point disabled.
HUB_HELP_URL = config("HUB_HELP_URL", default="")

# Quick Access click analytics. Optional, and off is a supported answer: the
# beacon endpoint keeps returning 204 either way, so turning this off costs a
# count and never a click. Rows carry a link's stable key and never its URL —
# see apps/web/quick_access/analytics.py.
QUICK_ACCESS_CLICK_ANALYTICS = config(
    "QUICK_ACCESS_CLICK_ANALYTICS", default=True, cast=bool
)

# Inertia's HTTP client reads the XSRF-TOKEN cookie and echoes it back as the
# X-XSRF-TOKEN header, so we align Django's CSRF cookie/header names with that.
CSRF_HEADER_NAME = "HTTP_X_XSRF_TOKEN"
CSRF_COOKIE_NAME = "XSRF-TOKEN"

# ---------------------------------------------------------------------------
# django-allauth — Microsoft (Entra ID) SSO
# ---------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

LOGIN_URL = "/"
LOGIN_REDIRECT_URL = "/dashboard"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"

# The custom user model (apps/user) has no username field: allauth logs in
# with email and never touches a username. Signup collects email + password
# only (no username), matching the email-based user.
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_USER_MODEL_EMAIL_FIELD = "email"
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_UNIQUE_EMAIL = True

SOCIALACCOUNT_PROVIDERS = {
    "microsoft": {
        "APP": {
            "client_id": config("MICROSOFT_CLIENT_ID", default=""),
            "secret": config("MICROSOFT_CLIENT_SECRET", default=""),
            "settings": {
                # "common" (personal + work/school), "organizations",
                # "consumers", or a specific tenant id.
                "tenant": config("MICROSOFT_TENANT", default="common"),
            },
        }
    }
}

# New signups (including the first Microsoft SSO login) are added to this
# group automatically — see apps/user/signals.py. Roles are Django Groups:
# create them in the admin (/admin/auth/group/), grant permissions there,
# and members inherit them. The default group is seeded by the
# 0002_default_user_group migration.
DEFAULT_USER_GROUP = "Users"

# ---------------------------------------------------------------------------
# Sentry (error tracking — sentry.io or PostHog error tracking)
# ---------------------------------------------------------------------------
# Sentry SDK events are ingested by sentry.io, or by PostHog's error tracking
# feature (it accepts the same Sentry DSN format — see PostHog docs). Leave
# SENTRY_DSN empty to disable the SDK entirely.
SENTRY_DSN = config("SENTRY_DSN", default="")
SENTRY_ENVIRONMENT = config(
    "SENTRY_ENVIRONMENT", default="development" if DEBUG else "production"
)
SENTRY_TRACES_SAMPLE_RATE = config("SENTRY_TRACES_SAMPLE_RATE", default=0.0, cast=float)
SENTRY_SEND_DEFAULT_PII = config("SENTRY_SEND_DEFAULT_PII", default=False, cast=bool)

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=SENTRY_SEND_DEFAULT_PII,
        integrations=[
            DjangoIntegration(),
            # Forward app logs as Sentry events at ERROR+ (breadcrumbs at INFO+).
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
    )
