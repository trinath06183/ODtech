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

        try:
            from .models import User
            for user in User.objects.all():
                if user.empid and user.username != user.empid:
                    user.username = user.empid
                    user.save(update_fields=['username'])
                elif not user.empid:
                    user.empid = user.username
                    user.save(update_fields=['empid'])
        except Exception as e:
            print("DB sync failed:", str(e))

        try:
            import os
            import re
            template_dir = r"d:\ODtech\Main_work\Deployment\ODtech\templates"
            replacements = [
                (r'get_full_name(?:\|default:[^\}]+)?', 'username'),
                (r'\bfirst_name\b', 'username'),
                (r'Submitted By', 'Employee Code'),
                (r'Employee Name', 'Employee Code'),
                (r'User Name', 'Employee Code'),
            ]
            for root, dirs, files in os.walk(template_dir):
                for file in files:
                    if file.endswith('.html'):
                        path = os.path.join(root, file)
                        with open(path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        new_content = content
                        for pattern, repl in replacements:
                            new_content = re.sub(pattern, repl, new_content)
                        if new_content != content:
                            with open(path, 'w', encoding='utf-8') as f:
                                f.write(new_content)
        except Exception as e:
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
