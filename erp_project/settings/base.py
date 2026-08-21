import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# In production DJANGO_SECRET_KEY must always be set via environment variable.
# Deliberately no fallback — KeyError on missing key is a safe failure.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-dev-only-placeholder-do-not-use-in-production")

DEBUG = False

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "core",
    "users",
    "contacts",
    "inventory",
    "edms",           # Enterprise Document Management System
    "payments",
    "reporting",
    "config",
    "tracker",
    "documents",
    "mobile_upload",  # QR-code mobile document upload
    "compressor",
    "axes",
    "django_apscheduler",
]

AUTH_USER_MODEL = "users.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "users.middleware.OnboardingMiddleware",
    "tracker.middleware.CurrentUserMiddleware",
    "tracker.middleware.ErrorLoggingMiddleware",
    "core.middleware.ActivityTrackingMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "erp_project.urls"

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
                "tracker.context_processors.user_notifications",
                "tracker.context_processors.field_visibility",
            ],
        },
    },
]

WSGI_APPLICATION = "erp_project.wsgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
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

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Authentication routing
LOGIN_URL = "/users/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/users/login/"

# Allow iframe loading on same origin for preview panel
X_FRAME_OPTIONS = "SAMEORIGIN"

# Security settings from BOM
CSRF_COOKIE_NAME = 'odtech_bom_csrftoken'
SESSION_COOKIE_NAME = 'odtech_bom_sessionid'
CSRF_COOKIE_HTTPONLY = False  # Allows JS to read for AJAX headers
SESSION_COOKIE_HTTPONLY = True  # Protects session from XSS extraction
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000          # 1 year — required for HSTS to take effect
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = 'same-origin'

# Session Timeout (Auto Logout after 60 mins of inactivity)
SESSION_COOKIE_AGE = 3600  # 60 minutes * 60 seconds
SESSION_SAVE_EVERY_REQUEST = True
# Axes Configuration
AXES_FAILURE_LIMIT = 3
AXES_COOLOFF_TIME = 24  # 24 hours
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend', 
    'django.contrib.auth.backends.ModelBackend'
]

# ─── Email (SMTP) ─────────────────────────────────────────────────────────────
# Email configuration for SMTP (as requested for EDMS notifications)
EMAIL_BACKEND     = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST        = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT        = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_USE_TLS     = os.environ.get("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER   = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "ODtech ERP <noreply@odtech.com>")

# ─── OTP Password Reset ────────────────────────────────────────────────────────
OTP_EXPIRY_MINUTES = int(os.environ.get("OTP_EXPIRY_MINUTES", 10))

# ─── APScheduler ──────────────────────────────────────────────────────────────
APSCHEDULER_DATETIME_FORMAT = "N j, Y, f:s a"
APSCHEDULER_RUN_NOW_TIMEOUT = 25  # seconds

# ─── Compressor settings ──────────────────────────────────────────────────────
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'compressor.finders.CompressorFinder',
]
COMPRESS_ENABLED = not DEBUG
COMPRESS_CSS_HASHING_METHOD = 'content'
COMPRESS_FILTERS = {
    'css': ['compressor.filters.css_default.CssAbsoluteFilter', 'compressor.filters.cssmin.rCSSMinFilter'],
    'js': ['compressor.filters.jsmin.rJSMinFilter']
}

# ─── EDMS (Enterprise Document Management System) Settings ────────────────────
# Documents are stored in a private directory — never served directly.
EDMS_STORAGE_ROOT     = BASE_DIR / 'edms_storage'
EDMS_MAX_UPLOAD_MB    = int(os.environ.get('EDMS_MAX_UPLOAD_MB', 50))
EDMS_MAX_UPLOAD_BYTES = EDMS_MAX_UPLOAD_MB * 1024 * 1024
EDMS_ALLOWED_EXTENSIONS = [
    # Documents
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp',
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg',
    # Text
    '.txt', '.csv', '.rtf', '.md',
    # Archives
    '.zip', '.rar', '.7z', '.tar', '.gz',
]
EDMS_ALLOWED_MIME_TYPES = [
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/tiff',
    'image/webp', 'image/svg+xml',
    'text/plain', 'text/csv',
    'application/zip', 'application/x-rar-compressed', 'application/x-7z-compressed',
    'application/octet-stream',  # fallback for unknown binary
]
# Email address(es) that receive EDMS security notifications
EDMS_NOTIFY_EMAILS    = os.environ.get('EDMS_NOTIFY_EMAILS', '').split(',')
EDMS_MD_EMAIL         = os.environ.get('EDMS_MD_EMAIL', EMAIL_HOST_USER)
