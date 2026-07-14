from .base import *

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", ".ngrok-free.dev", "*"]
CSRF_TRUSTED_ORIGINS = ["https://*.ngrok-free.dev", "http://*.ngrok-free.dev"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "odtech_db",
        "USER": "postgres",
        "PASSWORD": "1111",
        "HOST": "localhost",
        "PORT": "5432",
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
