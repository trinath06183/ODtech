from django.apps import AppConfig


class TrackerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tracker'

    def ready(self):
        import tracker.signals
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE tracker_productexpense ADD COLUMN expense_type varchar(20) DEFAULT 'PER_UNIT';")
        except Exception:
            pass
