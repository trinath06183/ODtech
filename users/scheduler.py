"""
APScheduler — In-process job scheduler
=======================================
Jobs registered here run automatically inside the Django process.
No extra services (Redis, Celery) needed.

Jobs scheduled:
  • send_payment_reminders  — daily at 08:00 IST (configurable)
  • cleanup_expired_otps    — hourly cleanup of expired OTP tokens
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.conf import settings
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.models import DjangoJobExecution

logger = logging.getLogger(__name__)

_scheduler = None  # module-level singleton guard
_lock_file = None  # keeps process file lock open for the lifetime of the worker


def send_payment_reminders_job():
    """APScheduler wrapper for the send_reminders management command."""
    from django.core.management import call_command
    try:
        logger.info("APScheduler: Running send_reminders...")
        call_command('send_reminders', '--days', '3')
        logger.info("APScheduler: send_reminders complete.")
    except Exception as exc:
        logger.error(f"APScheduler: send_reminders failed: {exc}", exc_info=True)


def backup_db_job():
    """APScheduler wrapper for the backup_db management command."""
    from django.core.management import call_command
    try:
        logger.info("APScheduler: Running backup_db...")
        call_command('backup_db')
        logger.info("APScheduler: backup_db complete.")
    except Exception as exc:
        logger.error(f"APScheduler: backup_db failed: {exc}", exc_info=True)


def cleanup_expired_otps_job():
    """Remove expired/used OTP tokens to keep the table clean."""
    from django.utils import timezone
    from users.models import OTPToken
    try:
        deleted, _ = OTPToken.objects.filter(
            expires_at__lt=timezone.now()
        ).delete()
        if deleted:
            logger.info(f"APScheduler: Cleaned up {deleted} expired OTP token(s).")
    except Exception as exc:
        logger.error(f"APScheduler: OTP cleanup failed: {exc}", exc_info=True)


def cleanup_old_executions_job():
    """Prune old APScheduler execution records (keep last 100)."""
    try:
        DjangoJobExecution.objects.delete_old_job_executions(max_age=86400)  # 24h
    except Exception as exc:
        logger.error(f"APScheduler: Execution cleanup failed: {exc}", exc_info=True)


def prune_logs_job():
    """APScheduler wrapper for the prune_logs management command."""
    from django.core.management import call_command
    try:
        logger.info("APScheduler: Running prune_logs...")
        call_command('prune_logs', '--days', '90')
        logger.info("APScheduler: prune_logs complete.")
    except Exception as exc:
        logger.error(f"APScheduler: prune_logs failed: {exc}", exc_info=True)


def start():
    """Start the background scheduler. Call once from users.apps.UsersConfig.ready()."""
    global _scheduler, _lock_file
    if _scheduler is not None:
        return  # already started

    # Use file locking on Linux/Unix so ONLY ONE Gunicorn worker starts the scheduler.
    # Without this, all 3 Gunicorn workers start duplicate schedulers and send duplicate emails.
    try:
        import fcntl
        import tempfile
        import os
        lock_path = os.path.join(tempfile.gettempdir(), 'odtech_apscheduler.lock')
        _lock_file = open(lock_path, 'wb')
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, IOError):
        logger.info("APScheduler: Another worker process already owns the scheduler lock. Skipping.")
        return
    except ImportError:
        pass  # Windows development environment
    except Exception as exc:
        logger.warning(f"APScheduler: File lock check skipped: {exc}")

    # Read reminder schedule from settings (default 08:00 IST)
    reminder_hour = getattr(settings, 'REMINDER_HOUR', 8)
    reminder_minute = getattr(settings, 'REMINDER_MINUTE', 0)
    timezone_str = getattr(settings, 'TIME_ZONE', 'Asia/Kolkata')

    _scheduler = BackgroundScheduler(timezone=timezone_str)
    _scheduler.add_jobstore(DjangoJobStore(), "default")

    # Daily payment reminder
    _scheduler.add_job(
        send_payment_reminders_job,
        trigger=CronTrigger(hour=reminder_hour, minute=reminder_minute, timezone=timezone_str),
        id="send_payment_reminders",
        name="Daily payment due-date reminders",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=600,  # 10 minutes grace
    )

    # Hourly OTP cleanup
    _scheduler.add_job(
        cleanup_expired_otps_job,
        trigger=CronTrigger(minute=0),  # top of every hour
        id="cleanup_expired_otps",
        name="Cleanup expired OTP tokens",
        replace_existing=True,
        max_instances=1,
    )

    # Daily old-execution pruning (at midnight)
    _scheduler.add_job(
        cleanup_old_executions_job,
        trigger=CronTrigger(hour=0, minute=30),
        id="cleanup_old_executions",
        name="Cleanup old APScheduler executions",
        replace_existing=True,
        max_instances=1,
    )

    # Daily database backup (at 11:30 PM)
    _scheduler.add_job(
        backup_db_job,
        trigger=CronTrigger(hour=23, minute=30),
        id="backup_db_job",
        name="Daily database backup to admin email",
        replace_existing=True,
        max_instances=1,
    )

    # Daily system log pruning (at 02:00 AM - keeps last 90 days)
    _scheduler.add_job(
        prune_logs_job,
        trigger=CronTrigger(hour=2, minute=0, timezone=timezone_str),
        id="prune_logs_job",
        name="Daily system log pruning (older than 90 days)",
        replace_existing=True,
        max_instances=1,
    )

    try:
        _scheduler.start()
        logger.info(
            f"APScheduler started. Payment reminders scheduled at {reminder_hour:02d}:{reminder_minute:02d} {timezone_str}."
        )
    except Exception as exc:
        logger.error(f"APScheduler failed to start: {exc}", exc_info=True)
