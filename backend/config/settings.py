"""Django settings. Every environment-specific value comes from env vars (django-environ)."""

from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, ["http://localhost:5173", "http://127.0.0.1:5173"]),
    SECURE_COOKIES=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-secret-key-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "apps.core",
    "apps.accounts",
    "apps.customers",
    "apps.catalog",
    "apps.invoices",
    "apps.payments",
    "apps.messaging",
    "apps.audit",
    "apps.recurring",
    "apps.quotes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.CurrentBusinessMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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

DATABASES = {
    "default": env.db(
        "DATABASE_URL", default="postgres://invoicing:invoicing@localhost:5432/invoicing"
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Lusaka"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = env.path("MEDIA_ROOT", default=BASE_DIR / "media")

# Generated PDFs (and later logos). Local disk by default; set S3_BUCKET for Cloudflare R2 / S3.
if env("S3_BUCKET", default=""):
    _default_storage = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("S3_BUCKET"),
            "endpoint_url": env("S3_ENDPOINT_URL", default=None),
            "access_key": env("S3_ACCESS_KEY_ID", default=None),
            "secret_key": env("S3_SECRET_ACCESS_KEY", default=None),
            "default_acl": "private",
            "querystring_auth": True,
        },
    }
else:
    _default_storage = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
STORAGES = {
    "default": _default_storage,
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
if DEBUG:
    STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}

# Where customers open invoices. Same origin as the app (the SPA proxies /i/ to Django).
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", default="http://localhost:5173")
ADMIN_URL = env("ADMIN_URL", default="admin/")

# Email: console in development; set EMAIL_BACKEND to an anymail backend in production, e.g.
# anymail.backends.resend.EmailBackend with ANYMAIL_RESEND_API_KEY.
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="invoices@localhost")
ANYMAIL = {
    k.removeprefix("ANYMAIL_"): v for k, v in env.ENVIRON.items() if k.startswith("ANYMAIL_")
}

# --- Auth: Django sessions + CSRF (SPA is served from the same site; no JWTs in the browser).
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # the SPA reads it and echoes it in X-CSRFToken
SESSION_COOKIE_SECURE = env("SECURE_COOKIES")
CSRF_COOKIE_SECURE = env("SECURE_COOKIES")
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.Pagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_RATES": {"auth": "10/min"},
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Invoicing API",
    "DESCRIPTION": "Invoices, customers and payments for Zambian small businesses.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "CurrencyEnum": "apps.accounts.models.Currency",
        "InvoiceStatusEnum": "apps.invoices.models.Invoice.Status",
        "InvoiceDisplayStatusEnum": "apps.invoices.models.DISPLAY_STATUS_CHOICES",
        "QuoteStatusEnum": "apps.quotes.models.Quote.Status",
        "QuoteDisplayStatusEnum": "apps.quotes.models.QUOTE_DISPLAY_STATUS_CHOICES",
        "DeliveryStatusEnum": "apps.messaging.models.Delivery.Status",
    },
}

CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
# Online payments (Lenco by BroadPay). Each business connects its own Lenco account in Settings;
# keys are stored encrypted with FIELD_ENCRYPTION_KEY (a Fernet key; generate one with
# `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="")
LENCO_LIVE_API_URL = env("LENCO_LIVE_API_URL", default="https://api.lenco.co/access/v2")
# Lenco's docs don't publish the sandbox API host; confirm it with Lenco and override if needed.
LENCO_SANDBOX_API_URL = env("LENCO_SANDBOX_API_URL", default="https://sandbox.lenco.co/access/v2")
LENCO_LIVE_WIDGET_URL = "https://pay.lenco.co/js/v1/inline.js"
LENCO_SANDBOX_WIDGET_URL = "https://pay.sandbox.lenco.co/js/v1/inline.js"

CELERY_BEAT_SCHEDULE = {
    # Times are Africa/Lusaka (CELERY_TIMEZONE).
    "generate-recurring-invoices": {
        "task": "apps.recurring.tasks.generate_recurring_invoices",
        "schedule": crontab(hour=6, minute=0),
    },
    "send-overdue-reminders": {
        "task": "apps.messaging.tasks.send_overdue_reminders",
        "schedule": crontab(hour=9, minute=0),
    },
    # Webhooks can be missed; re-check online payments still waiting for an answer.
    "reconcile-online-payments": {
        "task": "apps.payments.tasks.reconcile_payments",
        "schedule": crontab(minute="*/10"),
    },
}

# --- WhatsApp Business Cloud API (Phase 2). Leave the token empty to keep click-to-chat only.
WHATSAPP_TOKEN = env("WHATSAPP_TOKEN", default="")
WHATSAPP_PHONE_NUMBER_ID = env("WHATSAPP_PHONE_NUMBER_ID", default="")
WHATSAPP_APP_SECRET = env("WHATSAPP_APP_SECRET", default="")  # verifies webhook signatures
WHATSAPP_VERIFY_TOKEN = env("WHATSAPP_VERIFY_TOKEN", default="")  # webhook subscription check
WHATSAPP_API_VERSION = env("WHATSAPP_API_VERSION", default="v21.0")
WHATSAPP_TEMPLATE_LANGUAGE = env("WHATSAPP_TEMPLATE_LANGUAGE", default="en")
WHATSAPP_TEMPLATES = {
    "invoice": env("WHATSAPP_TEMPLATE_INVOICE", default="invoice_new"),
    "reminder": env("WHATSAPP_TEMPLATE_REMINDER", default="invoice_reminder"),
    "quote": env("WHATSAPP_TEMPLATE_QUOTE", default="quote_new"),
}
