"""
Management Command: prune_logs
==============================
Prunes old log records (SystemActivityLog, ErrorLog, AuditLog)
older than a configured number of days (default: 90 days).

Can be run manually:
    python manage.py prune_logs --days 90
Or automatically via APScheduler daily at 02:00 AM IST.
"""

from datetime import timedelta
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Prune system activity, error, and audit logs older than N days."

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=90,
            help='Retention period in days (default: 90). Older logs are deleted.',
        )

    def handle(self, *args, **options):
        days = options['days']
        cutoff_date = timezone.now() - timedelta(days=days)
        self.stdout.write(
            f"prune_logs: Deleting logs older than {days} days (before {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')})..."
        )

        total_deleted = 0

        # 1. Prune SystemActivityLog
        try:
            from core.models import SystemActivityLog
            deleted_activity, _ = SystemActivityLog.objects.filter(timestamp__lt=cutoff_date).delete()
            self.stdout.write(self.style.SUCCESS(f"  • Deleted {deleted_activity} SystemActivityLog records."))
            total_deleted += deleted_activity
        except Exception as e:
            logger.error(f"prune_logs: Failed to prune SystemActivityLog: {e}", exc_info=True)
            self.stderr.write(f"  • Error pruning SystemActivityLog: {e}")

        # 2. Prune ErrorLog
        try:
            from tracker.models import ErrorLog
            deleted_errors, _ = ErrorLog.objects.filter(timestamp__lt=cutoff_date).delete()
            self.stdout.write(self.style.SUCCESS(f"  • Deleted {deleted_errors} ErrorLog records."))
            total_deleted += deleted_errors
        except Exception as e:
            logger.error(f"prune_logs: Failed to prune ErrorLog: {e}", exc_info=True)
            self.stderr.write(f"  • Error pruning ErrorLog: {e}")

        # 3. Prune AuditLog (retain for 180 days or 2x days if specified)
        audit_cutoff = timezone.now() - timedelta(days=max(days, 180))
        try:
            from tracker.models import AuditLog
            deleted_audit, _ = AuditLog.objects.filter(timestamp__lt=audit_cutoff).delete()
            self.stdout.write(self.style.SUCCESS(f"  • Deleted {deleted_audit} AuditLog records (older than {max(days, 180)} days)."))
            total_deleted += deleted_audit
        except Exception as e:
            logger.error(f"prune_logs: Failed to prune AuditLog: {e}", exc_info=True)
            self.stderr.write(f"  • Error pruning AuditLog: {e}")

        self.stdout.write(self.style.SUCCESS(f"prune_logs: Complete. Total {total_deleted} old log entries removed."))
        logger.info(f"prune_logs: Cleaned up {total_deleted} log records older than {days} days.")
