"""AppConfig for the EDMS Django app."""
from django.apps import AppConfig


class EdmsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'edms'
    verbose_name = 'Enterprise Document Management'

    def ready(self):
        # Import signals so they are registered on startup.
        import edms.signals  # noqa: F401
