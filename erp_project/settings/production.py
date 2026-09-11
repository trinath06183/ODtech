import os

from .base import *

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() in ("true", "1")

env_hosts = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")
    if host.strip()
]
ALLOWED_HOSTS = list(set([
    "localhost",
    "127.0.0.1",
    ".ts.net",
    ".duckdns.org",
    ".ngrok-free.dev",
    ".ngrok.app",
    ".ngrok.io",
] + env_hosts))

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["POSTGRES_DB"],
        "USER": os.environ["POSTGRES_USER"],
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

# Include default ngrok, Tailscale, and DuckDNS trusted origins along with env origins
env_origins = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
CSRF_TRUSTED_ORIGINS = list(set([
    "https://*.ts.net",
    "https://*.duckdns.org",
    "http://*.duckdns.org",
    "https://*.ngrok-free.dev",
    "https://*.ngrok.app",
    "https://*.ngrok.io",
] + env_origins))

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False  # Must be False so JavaScript AJAX can read the CSRF token
SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "true").lower() == "true"

