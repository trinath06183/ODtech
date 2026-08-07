"""
Management Command: backup_db
==============================
Runs the server's odtech-autobackup script and emails the resulting
.tar.gz file to the admin_backup_email configured in Company Settings.

Scheduled by APScheduler daily at 23:30 IST via users/scheduler.py.
"""

import os
import glob
import subprocess
import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import EmailMessage
from django.utils import timezone

logger = logging.getLogger(__name__)

BACKUP_DIR = "/home/server_admin/backups"
BACKUP_SCRIPT = "/usr/local/bin/odtech-autobackup"


class Command(BaseCommand):
    help = "Create a PostgreSQL system backup and email it to the admin."

    def handle(self, *args, **options):
        self.stdout.write("backup_db: Starting backup...")

        # ── 1. Get admin backup email from Company Settings ───────────────────
        try:
            from config.models import CompanyProfile
            profile = CompanyProfile.objects.first()
            admin_email = (profile.admin_backup_email if profile and profile.admin_backup_email
                           else None)
        except Exception:
            admin_email = None

        # Fall back to EMAIL_HOST_USER if no company profile email is set
        if not admin_email:
            admin_email = getattr(settings, 'EDMS_MD_EMAIL', None) or settings.EMAIL_HOST_USER

        if not admin_email:
            self.stderr.write("ERROR: No admin backup email configured. "
                              "Set it in Company Settings or EMAIL_HOST_USER in .env")
            return

        # ── 2. Run the backup script ──────────────────────────────────────────
        if not os.path.exists(BACKUP_SCRIPT):
            msg = f"Backup script not found at {BACKUP_SCRIPT}"
            logger.error("backup_db: %s", msg)
            self._send_failure_email(admin_email, msg)
            self.stderr.write(f"ERROR: {msg}")
            return

        try:
            result = subprocess.run(
                [BACKUP_SCRIPT],
                capture_output=True,
                text=True,
                timeout=300,  # 5 min max
            )
        except subprocess.TimeoutExpired:
            msg = "Backup script timed out after 5 minutes."
            logger.error("backup_db: %s", msg)
            self._send_failure_email(admin_email, msg)
            self.stderr.write(f"ERROR: {msg}")
            return

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            logger.error("backup_db: Backup script failed: %s", error_msg)
            self._send_failure_email(admin_email, error_msg)
            self.stderr.write(f"ERROR: Backup script failed: {error_msg}")
            return

        self.stdout.write("backup_db: Backup script ran successfully.")

        # ── 3. Find the newest backup file ────────────────────────────────────
        if not os.path.exists(BACKUP_DIR):
            msg = f"Backup directory not found: {BACKUP_DIR}"
            logger.error("backup_db: %s", msg)
            return

        all_backups = sorted(
            glob.glob(os.path.join(BACKUP_DIR, "odtech_backup_*.tar.gz")),
            reverse=True,
        )

        if not all_backups:
            msg = "Backup script ran but no .tar.gz file was found."
            logger.error("backup_db: %s", msg)
            self._send_failure_email(admin_email, msg)
            return

        latest_backup = all_backups[0]
        backup_size_mb = os.path.getsize(latest_backup) / (1024 * 1024)
        backup_name = os.path.basename(latest_backup)

        self.stdout.write(f"backup_db: Found backup: {backup_name} ({backup_size_mb:.1f} MB)")

        # ── 4. Clean up old backups (keep latest 5) ───────────────────────────
        for old_backup in all_backups[5:]:
            try:
                os.remove(old_backup)
                logger.info("backup_db: Removed old backup: %s", old_backup)
            except Exception as e:
                logger.warning("backup_db: Could not remove old backup %s: %s", old_backup, e)

        # ── 5. Email the backup ───────────────────────────────────────────────
        MAX_ATTACH_MB = 20
        timestamp = timezone.now().strftime("%d %b %Y, %I:%M %p IST")

        email = EmailMessage(
            subject=f"[ODtech ERP] Daily Backup — {timestamp}",
            body=(
                f"Hi Admin,\n\n"
                f"Your daily automatic backup has been created successfully.\n\n"
                f"  • File   : {backup_name}\n"
                f"  • Size   : {backup_size_mb:.1f} MB\n"
                f"  • Time   : {timestamp}\n\n"
                + (
                    "The backup file is attached to this email.\n"
                    if backup_size_mb <= MAX_ATTACH_MB
                    else f"⚠ The backup is {backup_size_mb:.1f} MB — too large to attach. "
                         f"Please download it manually from the Backup & Restore panel.\n"
                )
                + "\nThis is an automated message from ODtech ERP."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[admin_email],
        )

        if backup_size_mb <= MAX_ATTACH_MB:
            with open(latest_backup, "rb") as f:
                email.attach(backup_name, f.read(), "application/gzip")
            self.stdout.write(f"backup_db: Attaching backup ({backup_size_mb:.1f} MB) to email...")
        else:
            self.stdout.write(
                f"backup_db: Backup too large ({backup_size_mb:.1f} MB), sending notification only."
            )

        try:
            email.send(fail_silently=False)
            logger.info("backup_db: Backup email sent to %s", admin_email)
            self.stdout.write(self.style.SUCCESS(f"backup_db: Done. Email sent to {admin_email}."))
        except Exception as e:
            logger.error("backup_db: Failed to send backup email: %s", e, exc_info=True)
            self.stderr.write(f"ERROR: Could not send email: {e}")

    def _send_failure_email(self, admin_email: str, reason: str):
        """Send a failure notification email to the admin."""
        try:
            timestamp = timezone.now().strftime("%d %b %Y, %I:%M %p IST")
            EmailMessage(
                subject=f"[ODtech ERP] ⚠ Backup FAILED — {timestamp}",
                body=(
                    f"Hi Admin,\n\n"
                    f"The automatic backup scheduled for {timestamp} has FAILED.\n\n"
                    f"Reason: {reason}\n\n"
                    f"Please log in to the server and check the backup script manually.\n\n"
                    f"This is an automated message from ODtech ERP."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[admin_email],
            ).send(fail_silently=True)
        except Exception:
            pass
