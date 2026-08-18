import sys
from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'

    def ready(self):
        """
        Called once when Django finishes startup.
        Starts the APScheduler background scheduler (skipped during migrations,
        test runs, and management commands that don't need it).
        """
        # Avoid starting the scheduler during manage.py commands that don't need it,
        # and avoid double-start in development with auto-reloader (RUN_MAIN env var).
        import os
        skip_commands = {'migrate', 'makemigrations', 'collectstatic', 'shell', 'test'}
        running_command = sys.argv[1] if len(sys.argv) > 1 else ''

        if running_command in skip_commands:
            return

        pass

        # In dev, Django's auto-reloader launches a child process with RUN_MAIN=true.
        # We only start the scheduler in that child process (or in production).
        if os.environ.get('RUN_MAIN', 'false') == 'true' or not os.environ.get('DJANGO_SETTINGS_MODULE', '').endswith('development'):
            try:
                from . import scheduler
                scheduler.start()
            except Exception as exc:
                import logging
                logging.getLogger(__name__).error(
                    f"Could not start APScheduler: {exc}", exc_info=True
                )
