"""
Management command: send_reminders
====================================
Sends daily payment due-date reminder emails to Admin users.

Usage:
    python manage.py send_reminders [--days N]

Cron schedule (example — run daily at 08:00 IST):
    0 8 * * * /path/to/venv/python /path/to/manage.py send_reminders

APScheduler also calls this automatically if scheduler.py is running.
"""

from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone


class Command(BaseCommand):
    help = "Send daily payment due-date reminder emails to Admin users."

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=3,
            help='Number of days ahead to check for due payments (default: 3)',
        )

    def handle(self, *args, **options):
        days_ahead = options['days']
        today = timezone.localdate()
        cutoff = today + timezone.timedelta(days=days_ahead)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'[{timezone.now().strftime("%Y-%m-%d %H:%M:%S")}] Running payment reminders (due <= {days_ahead} days)...'
        ))

        # ── Collect due invoices ──────────────────────────────────────────────
        invoices = self._get_due_invoices(today, cutoff)

        overdue = [i for i in invoices if i['days_remaining'] < 0]
        due_today = [i for i in invoices if i['days_remaining'] == 0]
        due_soon = [i for i in invoices if 0 < i['days_remaining'] <= days_ahead]

        self.stdout.write(
            f'  Found: {len(overdue)} overdue, {len(due_today)} due today, {len(due_soon)} due soon'
        )

        if not invoices:
            self.stdout.write(self.style.SUCCESS('  No pending invoices. Skipping email.'))
            return

        # ── Send to all Admin users ───────────────────────────────────────────
        from users.models import User
        admins = User.objects.filter(role='Admin', is_active=True, email__isnull=False).exclude(email='')

        if not admins.exists():
            self.stdout.write(self.style.WARNING('  No active Admin users with email found.'))
            return

        sent_count = 0
        for admin in admins:
            try:
                self._send_reminder_email(
                    recipient=admin,
                    invoices=invoices,
                    overdue_count=len(overdue),
                    due_today_count=len(due_today),
                    due_soon_count=len(due_soon),
                    reminder_date=today.strftime('%d %B %Y'),
                )
                sent_count += 1
                self.stdout.write(f'  [OK] Sent to {admin.email}')
            except Exception as exc:
                self.stderr.write(f'  [FAIL] Failed to send to {admin.email}: {exc}')

        self.stdout.write(self.style.SUCCESS(f'  Done. Sent {sent_count} reminder email(s).'))

    # ──────────────────────────────────────────────────────────────────────────

    def _get_due_invoices(self, today, cutoff):
        """
        Previously queried billing documents for due invoices.
        The billing module has been replaced by EDMS — this reminder
        now returns an empty list. Future versions will query EDMS documents
        with payment tracking.
        """
        self.stdout.write(self.style.WARNING(
            '  Billing documents module removed. Payment reminders will use EDMS in future versions.'
        ))
        return []



    def _send_reminder_email(self, recipient, invoices, overdue_count,
                              due_today_count, due_soon_count, reminder_date):
        """Send the HTML reminder email to one recipient."""
        context = {
            'recipient_name': recipient.get_full_name() or recipient.username,
            'invoices': invoices,
            'overdue_count': overdue_count,
            'due_today_count': due_today_count,
            'due_soon_count': due_soon_count,
            'reminder_date': reminder_date,
        }
        subject = f"Payment Reminder ({reminder_date}) - ODtech ERP"
        html_content = render_to_string('users/payment_reminder_email.html', context)
        text_content = strip_tags(html_content)

        email = EmailMultiAlternatives(
            subject, text_content, from_email=None, to=[recipient.email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
