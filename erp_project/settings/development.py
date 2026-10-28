import os
from .base import *

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", ".ngrok-free.dev", "*"]
CSRF_TRUSTED_ORIGINS = ["https://*.ngrok-free.dev", "http://*.ngrok-free.dev"]

# Database configuration: uses Postgres if available, falls back to SQLite
USE_SQLITE = os.environ.get("USE_SQLITE", "false").lower() in ("true", "1", "yes")

if USE_SQLITE:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    try:
        import socket
        pg_host = os.environ.get("POSTGRES_HOST", "localhost")
        pg_port = int(os.environ.get("POSTGRES_PORT", "5432"))
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.8)
            s.connect((pg_host, pg_port))
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": os.environ.get("POSTGRES_DB", "odtech_db"),
                "USER": os.environ.get("POSTGRES_USER", "postgres"),
                "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "1111"),
                "HOST": pg_host,
                "PORT": str(pg_port),
            }
        }
    except Exception:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": BASE_DIR / "db.sqlite3",
            }
        }

# In development, emails are printed to the console by default (via base.py).
# To actually send out emails using a local SMTP server or a real Gmail account,
# create a `.env` file in the project root with the following:
#
#   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
#   EMAIL_HOST=smtp.gmail.com
#   EMAIL_PORT=587
#   EMAIL_USE_TLS=True
#   EMAIL_HOST_USER=your_email@gmail.com
#   EMAIL_HOST_PASSWORD=your_app_password
#   DEFAULT_FROM_EMAIL=ODtech ERP <your_email@gmail.com>
#
# (If using python-dotenv, ensure it is loaded, or export these manually in your shell)
