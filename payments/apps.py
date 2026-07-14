from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'payments'

    def ready(self):
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE payments_expense ADD COLUMN gst_amount decimal(15, 2) DEFAULT 0.00;")
        except Exception:
            pass
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE payments_expense ADD COLUMN payload text;")
        except Exception:
            pass
