"""
Django settings for the Fresh Trace project.
Environment-driven so the SAME settings file works for:
  - Local development -> SQLite
  - Production        -> PostgreSQL
"""
import os
from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Core / Security -------------------------------------------------------
SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-key-change-in-production')
DEBUG = config('DEBUG', default=True, cast=bool)

# Allow all hosts in dev / ngrok tunnels to prevent DisallowedHost errors
ALLOWED_HOSTS = ['*']

# Render terminates HTTPS at its own proxy and forwards plain HTTP internally,
# so without this Django would think every request is insecure and could
# loop on redirects / reject CSRF-protected form posts.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS = [
    'https://*.ngrok-free.dev',
    'https://*.ngrok-free.app',
    'https://*.ngrok.io',
    'https://*.ngrok.app',
    'https://upon-washday-aerobics.ngrok-free.dev',
    'http://127.0.0.1:8000',
    'http://localhost:8000',
    'http://127.0.0.1',
    'http://localhost',
]



# --- Applications ------------------------------------------------------------
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    # Channels
    'channels',

    # Local apps
    'accounts',
    'dashboard',
    'inventory',
    'orders',
    'tracking',
    'store',
    'customer_support',
    'whatsapp_webhook',
    'wa_flow',
]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # serves static files on Render, no Nginx needed
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'farm_market.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'store.context_processors.cart_summary',  # global cart count in navbar
                'dashboard.context_processors.dashboard_pending_counts',  # sidebar badge counts
            ],
        },
    },
]

WSGI_APPLICATION = 'farm_market.wsgi.application'
ASGI_APPLICATION = 'farm_market.asgi.application'

# --- Database ----------------------------------------------------------------
# Render (and most PaaS providers) set DATABASE_URL automatically when you
# attach a Postgres instance — if present, that always wins. Otherwise we
# fall back to the original DB_ENGINE switch for local dev (sqlite/postgres).
import dj_database_url

if config('DATABASE_URL', default=''):
    DATABASES = {
        'default': dj_database_url.config(
            default=config('DATABASE_URL'),
            conn_max_age=600,
            ssl_require=not DEBUG,
        )
    }
elif config('DB_ENGINE', default='sqlite') == 'postgres':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='freshtrace'),
            'USER': config('DB_USER', default='freshtrace_user'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# --- Custom User Model --------------------------------------------------------
AUTH_USER_MODEL = 'accounts.User'

# --- Password validation -------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    # Only rule: at least 8 characters (letters, numbers, anything).
    # Similarity-to-username, common-password, and all-numeric checks
    # removed on purpose, per project requirements.
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
]

# --- Internationalization -------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# --- Static & Media files -------------------------------------------------------
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG
        else "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Auth redirects --------------------------------------------------------
# Generic default; actual post-login redirect is role-based and handled
# in accounts.views.login_view, not by this static setting.
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'store:home'
LOGOUT_REDIRECT_URL = 'store:home'

# --- Messages (Bootstrap 5 alert classes) -----------------------------------
from django.contrib.messages import constants as messages
MESSAGE_TAGS = {
    messages.DEBUG: 'secondary',
    messages.INFO: 'info',
    messages.SUCCESS: 'success',
    messages.WARNING: 'warning',
    messages.ERROR: 'danger',
}

# --- Email (used for driver/farmer verification notifications) -------------
# Defaults to printing emails to the console so this works out-of-the-box in
# dev without any SMTP setup. Set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# plus EMAIL_HOST/EMAIL_HOST_USER/EMAIL_HOST_PASSWORD/EMAIL_PORT/EMAIL_USE_TLS
# in .env to send real emails in production.
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='Fresh Trace <no-reply@freshtrace.local>')

# --- Channels & WebSocket Configuration ------------------------------------
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }
}

# --- AI Chatbot Configuration ----------------------------------------------
HF_API_TOKEN = config('HF_API_TOKEN', default=config('OPENROUTER_API_KEY', default=''))
HF_CHAT_MODEL = config('AI_CHAT_MODEL', default='liquid/lfm-2.5-2.6b:free')

# --- WhatsApp Cloud API & Flow Configuration (wa_flow) ---------------------
WHATSAPP_TOKEN = config('WHATSAPP_TOKEN', default=config('WHATSAPP_ACCESS_TOKEN', default=''))
PHONE_NUMBER_ID = config('PHONE_NUMBER_ID', default=config('WHATSAPP_PHONE_NUMBER_ID', default=''))
FLOW_ID = config('FLOW_ID', default=config('WHATSAPP_FLOW_ID', default='1081930417655056'))
VERIFY_TOKEN = config('VERIFY_TOKEN', default=config('WHATSAPP_VERIFY_TOKEN', default='fresh_trace_wa_c5a23fd481477ef350e8944373ddfe3a'))
FLOW_PRIVATE_KEY_PEM = config('FLOW_PRIVATE_KEY_PEM', default=config('WHATSAPP_FLOW_PRIVATE_KEY_PEM', default=''))
FLOW_PRIVATE_KEY_PASSPHRASE = config('FLOW_PRIVATE_KEY_PASSPHRASE', default=None)
FLOW_PRIVATE_KEY_PATH = config('FLOW_PRIVATE_KEY_PATH', default=config('WHATSAPP_FLOW_PRIVATE_KEY_PATH', default='whatsapp_flow_private.pem'))
FLOW_MODE = config('FLOW_MODE', default=config('WHATSAPP_FLOW_MODE', default='draft'))

