"""
Management Command: backup_db
==============================
Runs pg_dump and creates backup archives (.sql.gz for email/DB-only,
and a complete system archive .tar.gz / .zip containing DB + all media files for Google Drive).
Emails the DB dump to the admin_backup_email and uploads the complete system backup to Google Drive.

Scheduled by APScheduler daily at 23:30 IST via users/scheduler.py.
"""

import os
import gzip
import glob
import shutil
import subprocess
import tarfile
import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import EmailMessage
from django.utils import timezone

logger = logging.getLogger(__name__)

BACKUP_DIR = "/home/server_admin/backups"


class Command(BaseCommand):
    help = "Dump the PostgreSQL database, create complete backup with media, email DB dump and upload complete backup to Google Drive."

    def add_arguments(self, parser):
        parser.add_argument(
            '--triggered-by',
            default='schedule',
            choices=['schedule', 'manual'],
            help='Who triggered this backup: schedule (nightly) or manual (user clicked Generate Now)',
        )
        parser.add_argument(
            '--full',
            action='store_true',
            default=True,
            help='Include media folder in Google Drive backup package (default: True)',
        )

    def handle(self, *args, **options):
        triggered_by = options.get('triggered_by', 'schedule')
        is_manual = triggered_by == 'manual'
        self.stdout.write("backup_db: Starting backup process...")

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

        # ── 7. Optional Google Drive upload (Complete Backup: DB + Media) ────
        self._upload_complete_backup_to_google_drive(dump_path, timestamp)

    def _upload_complete_backup_to_google_drive(self, dump_path: str, timestamp: str):
        """
        Package the database dump AND all media files into a complete archive
        (.tar.gz) and upload it directly to Google Drive.

        Required environment variables:
          GOOGLE_DRIVE_ENABLED=true
          GOOGLE_DRIVE_FOLDER_ID=<folder_id>
          GOOGLE_DRIVE_CREDENTIALS_PATH=/path/to/service_account.json
        """
        import os
        import tarfile

        drive_enabled = os.environ.get('GOOGLE_DRIVE_ENABLED', 'false').lower() == 'true'
        if not drive_enabled:
            return

        creds_path = os.environ.get(
            'GOOGLE_DRIVE_CREDENTIALS_PATH',
            '/home/server_admin/ODtech/google_drive_credentials.json'
        )
        folder_id = os.environ.get('GOOGLE_DRIVE_FOLDER_ID', '').strip()

        if not folder_id:
            logger.warning("backup_db: GOOGLE_DRIVE_FOLDER_ID not set. Skipping Drive upload.")
            return

        if not os.path.exists(creds_path):
            logger.warning(
                "backup_db: Google Drive credentials not found at %s. Skipping.", creds_path
            )
            return

        # ── 1. Create complete system archive (.tar.gz with DB + media) ──────
        complete_filename = f"odtech_complete_backup_{timestamp}.tar.gz"
        complete_archive_path = os.path.join(BACKUP_DIR, complete_filename)
        media_dir = getattr(settings, 'MEDIA_ROOT', '')

        self.stdout.write(f"backup_db: Packaging complete backup (DB + media) into {complete_filename}...")
        try:
            with tarfile.open(complete_archive_path, "w:gz") as tar:
                # Add database dump
                if os.path.exists(dump_path):
                    tar.add(dump_path, arcname=os.path.join("database", os.path.basename(dump_path)))
                # Add all media files if directory exists
                if media_dir and os.path.exists(media_dir):
                    tar.add(media_dir, arcname="media")

            complete_size_mb = os.path.getsize(complete_archive_path) / (1024 * 1024)
            self.stdout.write(f"backup_db: Complete archive created ({complete_size_mb:.1f} MB). Uploading to Google Drive...")
        except Exception as arc_err:
            logger.error("backup_db: Failed to create complete archive: %s", arc_err, exc_info=True)
            self.stderr.write(f"backup_db: Archive error: {arc_err}. Falling back to DB-only upload.")
            complete_archive_path = dump_path
            complete_filename = os.path.basename(dump_path)

        # ── 2. Upload to Google Drive (Supports Service Account & OAuth 2.0) ──
        try:
            import json
            from google.oauth2 import service_account
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            SCOPES = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive']

            # Inspect credentials file format (Service Account vs User OAuth Token)
            with open(creds_path, 'r', encoding='utf-8') as f:
                creds_data = json.load(f)

            if creds_data.get('type') == 'service_account':
                # Standard Service Account
                credentials = service_account.Credentials.from_service_account_file(
                    creds_path, scopes=SCOPES
                )
            else:
                # OAuth 2.0 User Token (refreshable)
                credentials = Credentials.from_authorized_user_file(creds_path, SCOPES)
                if credentials and credentials.expired and credentials.refresh_token:
                    credentials.refresh(Request())
                    # Persist refreshed token
                    with open(creds_path, 'w', encoding='utf-8') as f:
                        f.write(credentials.to_json())

            service = build('drive', 'v3', credentials=credentials)

            # Upload the complete archive
            file_metadata = {
                'name': complete_filename,
                'parents': [folder_id],
            }
            media = MediaFileUpload(complete_archive_path, mimetype='application/gzip', resumable=True)
            uploaded = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name,size'
            ).execute()
            file_id = uploaded.get('id')
            size_mb = int(uploaded.get('size', 0)) / (1024 * 1024)
            logger.info(
                "backup_db: Uploaded COMPLETE backup %s to Google Drive (id=%s, %.1f MB)",
                complete_filename, file_id, size_mb
            )
            self.stdout.write(
                self.style.SUCCESS(f"backup_db: Google Drive COMPLETE backup upload done — {complete_filename} ({size_mb:.1f} MB)")
            )

            # ── Prune old Drive complete backups (keep latest 7) ──────────────
            results = service.files().list(
                q=f"(name contains 'odtech_complete_backup_' or name contains 'odtech_db_') and '{folder_id}' in parents and trashed=false",
                fields="files(id, name, createdTime)",
                orderBy="createdTime desc",
            ).execute()
            all_files = results.get('files', [])
            for old_file in all_files[7:]:
                try:
                    service.files().delete(fileId=old_file['id']).execute()
                    logger.info(
                        "backup_db: Deleted old Drive backup %s (id=%s)",
                        old_file['name'], old_file['id']
                    )
                except Exception as del_err:
                    logger.warning("backup_db: Could not delete %s: %s", old_file['name'], del_err)

        except ImportError:
            logger.error(
                "backup_db: google-api-python-client not installed. "
                "Run: pip install google-api-python-client google-auth"
            )
        except Exception as e:
            logger.error("backup_db: Google Drive upload failed: %s", e, exc_info=True)
            self.stderr.write(f"backup_db: Google Drive upload error: {e}")
        finally:
            # Clean up local complete tar.gz if separate from dump to save server disk space (keep latest 3 local complete archives)
            try:
                all_local_complete = sorted(
                    glob.glob(os.path.join(BACKUP_DIR, "odtech_complete_backup_*.tar.gz")),
                    reverse=True
                )
                for old_local in all_local_complete[3:]:
                    try:
                        os.remove(old_local)
                    except Exception:
                        pass
            except Exception:
                pass

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
