"""
whatsapp_orders/settings.py
───────────────────────────
Django settings for whatsapp_orders project.
Uses python-decouple to load environment variables from parent or local .env.
"""

from pathlib import Path
from decouple import Config, RepositoryEnv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
PARENT_DIR = BASE_DIR.parent

# Look for .env in current directory or parent directory
env_path = BASE_DIR / ".env"
if not env_path.exists() and (PARENT_DIR / ".env").exists():
    env_path = PARENT_DIR / ".env"

if env_path.exists():
    config = Config(RepositoryEnv(str(env_path)))
else:
    from decouple import config

SECRET_KEY = config("SECRET_KEY", default="django-insecure-whatsapp-orders-secret-key-999")

DEBUG = config("DEBUG", default=True, cast=bool)

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third party apps
    "rest_framework",

    # Local apps
    "orders.apps.OrdersConfig",
    "whatsapp.apps.WhatsappConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "whatsapp_orders.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "whatsapp_orders.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Django REST Framework ───────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
}

# ── Celery Configuration ────────────────────────────────────────────────────
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = config("CELERY_TASK_ALWAYS_EAGER", default=True, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# ── WhatsApp Cloud API & Flow Configuration ──────────────────────────────────
WHATSAPP_ACCESS_TOKEN = config("WHATSAPP_ACCESS_TOKEN", default=config("WHATSAPP_TOKEN", default=""))
WHATSAPP_APP_SECRET = config("WHATSAPP_APP_SECRET", default="")
WHATSAPP_VERIFY_TOKEN = config("WHATSAPP_VERIFY_TOKEN", default="fresh_trace_wa_c5a23fd481477ef350e8944373ddfe3a")
WHATSAPP_PHONE_NUMBER_ID = config("WHATSAPP_PHONE_NUMBER_ID", default="1297443690119359")
WHATSAPP_WABA_ID = config("WHATSAPP_WABA_ID", default="1965689270778996")
WHATSAPP_FLOW_ID = config("WHATSAPP_FLOW_ID", default="1422173683118152")
WHATSAPP_FLOW_MODE = config("WHATSAPP_FLOW_MODE", default="draft")
WHATSAPP_API_VERSION = config("WHATSAPP_API_VERSION", default="v20.0")

# RSA Private Key PEM for WhatsApp Flow decrypting/encrypting
WHATSAPP_FLOW_PRIVATE_KEY = config("WHATSAPP_FLOW_PRIVATE_KEY", default=config("WHATSAPP_FLOW_PRIVATE_KEY_PEM", default=""))
WHATSAPP_FLOW_PRIVATE_KEY_PATH = config("WHATSAPP_FLOW_PRIVATE_KEY_PATH", default="whatsapp_flow_private.pem")

# ── Draft Testing Mode ───────────────────────────────────────────────────────
# When TESTING_MODE=True:
#   Outbound send_flow_trigger_message() is bypassed on incoming messages to avoid
#   Meta Graph API Error 139000 (Blocked By Integrity) for unpublished draft flows.
#   Flow is tested directly via WhatsApp Manager's "Preview Flow" tool.
TESTING_MODE = config("TESTING_MODE", default=config("DRAFT_MODE", default=True, cast=bool), cast=bool)

# ── Logging Configuration ───────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "whatsapp": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
        "orders": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}

