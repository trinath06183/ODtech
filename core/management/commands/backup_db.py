"""
Management Command: backup_db
==============================
Runs pg_dump directly (DB only — no media files) and emails the resulting
.sql.gz file to the admin_backup_email configured in Company Settings.

A direct download link to the Backup & Restore panel is also included.

Scheduled by APScheduler daily at 23:30 IST via users/scheduler.py.
"""

import os
import gzip
import glob
import shutil
import subprocess
import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import EmailMessage
from django.utils import timezone

logger = logging.getLogger(__name__)

BACKUP_DIR = "/home/server_admin/backups"


class Command(BaseCommand):
    help = "Dump the PostgreSQL database and email it to the admin (DB only)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--triggered-by',
            default='schedule',
            choices=['schedule', 'manual'],
            help='Who triggered this backup: schedule (nightly) or manual (user clicked Generate Now)',
        )

    def handle(self, *args, **options):
        triggered_by = options.get('triggered_by', 'schedule')
        is_manual = triggered_by == 'manual'
        self.stdout.write("backup_db: Starting DB-only backup...")

        # ── 1. Get admin backup email ─────────────────────────────────────────
        try:
            from config.models import CompanyProfile
            profile = CompanyProfile.objects.first()
            admin_email = (profile.admin_backup_email
                           if profile and profile.admin_backup_email else None)
        except Exception:
            admin_email = None

        if not admin_email:
            admin_email = getattr(settings, 'EDMS_MD_EMAIL', None) or settings.EMAIL_HOST_USER

        if not admin_email:
            self.stderr.write(
                "ERROR: No admin backup email configured. "
                "Set it in Company Settings or EMAIL_HOST_USER in .env"
            )
            return

        # ── 3. Load DB credentials from env ──────────────────────────────────
        env_path = "/home/server_admin/ODtech/.env"
        env = os.environ.copy()
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, _, val = line.partition('=')
                        env.setdefault(key.strip(), val.strip())

        db_name = env.get('POSTGRES_DB', settings.DATABASES['default'].get('NAME', ''))
        db_user = env.get('POSTGRES_USER', settings.DATABASES['default'].get('USER', ''))
        db_password = env.get('POSTGRES_PASSWORD', settings.DATABASES['default'].get('PASSWORD', ''))
        db_host = env.get('POSTGRES_HOST', settings.DATABASES['default'].get('HOST', 'localhost'))
        db_port = env.get('POSTGRES_PORT', str(settings.DATABASES['default'].get('PORT', '5432')))

        # ── 2. Build site URL for the download link ───────────────────────────
        site_url = env.get('SITE_URL', '').rstrip('/')
        if not site_url:
            trusted_origins = getattr(settings, 'CSRF_TRUSTED_ORIGINS', [])
            SKIP = ('localhost', '127.0.0.1', '::1')
            site_url = next(
                (o.rstrip('/') for o in trusted_origins
                 if '*' not in o and not any(s in o for s in SKIP)),
                None
            )
        if not site_url:
            site_url = "http://192.168.1.106"
        backup_panel_url = f"{site_url}/settings/backup/"

        if not db_name or not db_user:
            msg = "Database credentials not found in environment."
            logger.error("backup_db: %s", msg)
            self._send_failure_email(admin_email, msg, backup_panel_url)
            return

        # ── 4. Run pg_dump ────────────────────────────────────────────────────
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        dump_filename = f"odtech_db_{timestamp}.sql.gz"
        dump_path = os.path.join(BACKUP_DIR, dump_filename)

        # Auto-detect pg_dump binary — systemd services often have a stripped PATH
        pg_dump_bin = shutil.which("pg_dump")
        if not pg_dump_bin:
            # Search common PostgreSQL installation paths on Ubuntu/Debian
            candidates = []
            for pg_dir in ["/usr/bin", "/usr/local/bin"]:
                candidate = os.path.join(pg_dir, "pg_dump")
                if os.path.isfile(candidate):
                    candidates.append(candidate)
            # Also search versioned PostgreSQL directories
            import glob as _glob
            for versioned in sorted(_glob.glob("/usr/lib/postgresql/*/bin/pg_dump"), reverse=True):
                candidates.append(versioned)
            pg_dump_bin = candidates[0] if candidates else None

        if not pg_dump_bin:
            msg = (
                "pg_dump binary not found. PostgreSQL client tools may not be installed. "
                "Run: sudo apt-get install postgresql-client"
            )
            logger.error("backup_db: %s", msg)
            self._send_failure_email(admin_email, msg, backup_panel_url)
            self.stderr.write(f"ERROR: {msg}")
            return

        self.stdout.write(f"backup_db: Dumping database '{db_name}' using {pg_dump_bin}...")
        try:
            pg_env = env.copy()
            pg_env['PGPASSWORD'] = db_password

            pg_proc = subprocess.Popen(
                [
                    pg_dump_bin,
                    "--clean", "--if-exists",
                    "-U", db_user,
                    "-h", db_host,
                    "-p", db_port,
                    db_name,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=pg_env,
            )
            stdout, stderr = pg_proc.communicate(timeout=300)

            if pg_proc.returncode != 0:
                msg = stderr.decode(errors='replace') or "pg_dump failed with no error output."
                logger.error("backup_db: pg_dump failed: %s", msg)
                self._send_failure_email(admin_email, msg, backup_panel_url)
                self.stderr.write(f"ERROR: pg_dump failed: {msg}")
                return

            # Compress the dump
            with gzip.open(dump_path, 'wb') as gz:
                gz.write(stdout)

        except subprocess.TimeoutExpired:
            msg = "pg_dump timed out after 5 minutes."
            logger.error("backup_db: %s", msg)
            self._send_failure_email(admin_email, msg, backup_panel_url)
            self.stderr.write(f"ERROR: {msg}")
            return
        except FileNotFoundError:
            msg = f"pg_dump not found at '{pg_dump_bin}'. Run: sudo apt-get install postgresql-client"
            logger.error("backup_db: %s", msg)
            self._send_failure_email(admin_email, msg, backup_panel_url)
            self.stderr.write(f"ERROR: {msg}")
            return
        except Exception as e:
            logger.error("backup_db: Unexpected error: %s", e, exc_info=True)
            self._send_failure_email(admin_email, str(e), backup_panel_url)
            self.stderr.write(f"ERROR: {e}")
            return

        backup_size_mb = os.path.getsize(dump_path) / (1024 * 1024)
        self.stdout.write(f"backup_db: DB dump created: {dump_filename} ({backup_size_mb:.1f} MB)")

        # ── 5. Clean up old DB dumps (keep latest 5) ──────────────────────────
        all_dumps = sorted(
            glob.glob(os.path.join(BACKUP_DIR, "odtech_db_*.sql.gz")),
            reverse=True,
        )
        for old_dump in all_dumps[5:]:
            try:
                os.remove(old_dump)
            except Exception as e:
                logger.warning("backup_db: Could not remove old dump %s: %s", old_dump, e)

        # ── 6. Send email with attachment + download link ─────────────────────
        MAX_ATTACH_MB = 20
        can_attach = backup_size_mb <= MAX_ATTACH_MB
        now_str = timezone.now().strftime('%d %b %Y, %I:%M %p IST')
        date_str = timezone.now().strftime('%d %b %Y')

        if is_manual:
            subject = f"[ODtech ERP] ✅ Manual DB Backup — {date_str}"
            trigger_line = "This backup was manually triggered via the Backup & Restore panel."
        else:
            subject = f"[ODtech ERP] 🌙 Nightly Auto Backup — {date_str}"
            trigger_line = "This is your scheduled nightly automatic database backup (runs daily at 11:30 PM IST)."

        body = (
            f"Hi Admin,\n\n"
            f"{trigger_line}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"  Backup Summary\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"  • File     : {dump_filename}\n"
            f"  • Size     : {backup_size_mb:.1f} MB\n"
            f"  • Time     : {now_str}\n"
            f"  • Contents : Database only (.sql.gz)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )

        if can_attach:
            body += "📎 The database backup file (.sql.gz) is attached to this email.\n\n"
        else:
            body += (
                f"⚠ The backup file ({backup_size_mb:.1f} MB) exceeds the 20 MB email limit "
                f"and could not be attached directly.\n\n"
            )

        body += (
            f"📥 Download all backup files (DB + full media backup) from the Backup & Restore panel:\n"
            f"   {backup_panel_url}\n\n"
            f"💡 Tip: The panel also lets you download the complete system backup (.tar.gz) "
            f"which includes all uploaded media files.\n\n"
            f"— ODtech ERP (Automated Message)"
        )

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[admin_email],
        )

        if can_attach:
            with open(dump_path, "rb") as f:
                email.attach(dump_filename, f.read(), "application/gzip")
            self.stdout.write(f"backup_db: Attaching {dump_filename} to email...")

        try:
            email.send(fail_silently=False)
            logger.info("backup_db: Backup email sent to %s", admin_email)
            self.stdout.write(self.style.SUCCESS(
                f"backup_db: Done! Email sent to {admin_email}."
            ))
        except Exception as e:
            logger.error("backup_db: Failed to send email: %s", e, exc_info=True)
            self.stderr.write(f"ERROR: Could not send email: {e}")

    def _send_failure_email(self, admin_email: str, reason: str, panel_url: str):
        """Send a failure notification email to the admin."""
        try:
            timestamp = timezone.now().strftime("%d %b %Y, %I:%M %p IST")
            EmailMessage(
                subject=f"[ODtech ERP] ⚠ DB Backup FAILED — {timestamp}",
                body=(
                    f"Hi Admin,\n\n"
                    f"The automatic database backup scheduled for {timestamp} has FAILED.\n\n"
                    f"Reason:\n{reason}\n\n"
                    f"Please check the server and run the backup manually:\n"
                    f"{panel_url}\n\n"
                    f"This is an automated message from ODtech ERP."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[admin_email],
            ).send(fail_silently=True)
        except Exception:
            pass
