import os
from datetime import datetime
from django.core.management.base import BaseCommand
from django.core.mail import EmailMessage
from django.conf import settings
from config.models import CompanyProfile

class Command(BaseCommand):
    help = 'Backup SQLite Database and send to admin email'

    def handle(self, *args, **options):
        profile = CompanyProfile.objects.first()
        if not profile or not profile.admin_backup_email:
            self.stdout.write(self.style.WARNING("Backup email not configured in Company Settings. Skipping backup."))
            return

        db_path = settings.DATABASES['default']['NAME']
        
        if not os.path.exists(db_path):
            self.stdout.write(self.style.ERROR(f"Database file not found at {db_path}"))
            return

        date_str = datetime.now().strftime('%Y_%m_%d_%H%M')
        filename = f"db_backup_{date_str}.sqlite3"
        
        subject = f"[{profile.name}] Database Backup - {date_str}"
        body = f"Attached is the daily database backup for {profile.name} generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}."

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[profile.admin_backup_email],
        )

        with open(db_path, 'rb') as f:
            email.attach(filename, f.read(), 'application/x-sqlite3')

        try:
            email.send(fail_silently=False)
            self.stdout.write(self.style.SUCCESS(f"Successfully sent backup to {profile.admin_backup_email}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to send email: {e}"))
