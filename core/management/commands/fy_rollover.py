"""
Management Command: fy_rollover
=================================
Resets all document sequence counters in CompanyProfile to 0 at the
start of each new Financial Year (April 1st at 00:01 AM IST).

After rollover, the next auto-generated document number in each series
will start from 1, e.g. QTN/2627/001.

SAFETY:
  - Existing document numbers are NOT changed.
  - A --dry-run flag prints what would be reset without touching the DB.
  - An admin confirmation email is sent after a live rollover.

Scheduled by APScheduler on April 1 at 00:01 AM IST via users/scheduler.py.
Run manually: python manage.py fy_rollover [--dry-run]
"""

import logging
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

SEQUENCE_FIELDS = [
    ('seq_qtn', 'Quotation'),
    ('seq_inv', 'Invoice'),
    ('seq_pro', 'Proforma Invoice'),
    ('seq_chl', 'Delivery Challan'),
    ('seq_po',  'Purchase Order'),
    ('seq_crn', 'Credit Note'),
    ('seq_dbn', 'Debit Note'),
]


class Command(BaseCommand):
    help = "Reset all document sequence counters for the new Financial Year."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Print what would be reset without making any changes.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        today = date.today()
        fy_y = today.year if today.month >= 4 else today.year - 1
        new_fy = f"FY {fy_y}–{str(fy_y + 1)[2:]}"

        self.stdout.write(f"fy_rollover: {'[DRY RUN] ' if dry_run else ''}Starting FY rollover for {new_fy}...")

        try:
            from config.models import CompanyProfile
            profile = CompanyProfile.objects.first()
        except Exception as e:
            self.stderr.write(f"fy_rollover: ERROR loading CompanyProfile: {e}")
            return

        if not profile:
            self.stderr.write("fy_rollover: No CompanyProfile found. Cannot perform rollover.")
            return

        # Build summary of current → new values
        summary_lines = []
        for field, label in SEQUENCE_FIELDS:
            current_val = getattr(profile, field, 0)
            summary_lines.append(f"  {label:<25}: {current_val} → 0")
            if dry_run:
                self.stdout.write(f"  [DRY RUN] Would reset {field} from {current_val} to 0")

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"\nfy_rollover: [DRY RUN] No changes made. Run without --dry-run to apply."
            ))
            return

        # Perform the actual reset
        update_kwargs = {field: 0 for field, _ in SEQUENCE_FIELDS}
        try:
            for field, _ in SEQUENCE_FIELDS:
                setattr(profile, field, 0)
            profile.save()
            logger.info("fy_rollover: All sequences reset to 0 for %s", new_fy)
            self.stdout.write(self.style.SUCCESS(
                f"fy_rollover: All {len(SEQUENCE_FIELDS)} sequence counters reset to 0."
            ))
        except Exception as e:
            logger.error("fy_rollover: Failed to reset sequences: %s", e, exc_info=True)
            self.stderr.write(f"fy_rollover: ERROR: {e}")
            return

        # Send confirmation email to admin
        try:
            from django.core.mail import EmailMessage
            from config.models import CompanyProfile as CP
            p = CP.objects.first()
            admin_email = (p.admin_backup_email if p and p.admin_backup_email else None) or \
                          getattr(settings, 'EDMS_MD_EMAIL', None) or settings.EMAIL_HOST_USER
            company_name = p.name if p else "ODtech ERP"
        except Exception:
            admin_email = getattr(settings, 'EMAIL_HOST_USER', None)
            company_name = "ODtech ERP"

        if admin_email:
            try:
                now_str = timezone.now().strftime('%d %b %Y, %I:%M %p IST')
                reset_table = "\n".join(summary_lines)
                EmailMessage(
                    subject=f"[{company_name}] FY Rollover Completed — {new_fy}",
                    body=(
                        f"Hi Admin,\n\n"
                        f"The Financial Year document sequence rollover has been completed successfully.\n\n"
                        f"New Financial Year : {new_fy}\n"
                        f"Completed at       : {now_str}\n\n"
                        f"Sequences Reset:\n{reset_table}\n\n"
                        f"All future documents will now be numbered starting from 1 in the new FY.\n"
                        f"Existing document numbers remain unchanged.\n\n"
                        f"— {company_name} (Automated System)"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[admin_email],
                ).send(fail_silently=True)
                logger.info("fy_rollover: Confirmation email sent to %s", admin_email)
            except Exception as e:
                logger.warning("fy_rollover: Could not send confirmation email: %s", e)
