"""
Management Command: send_daily_expense_report
==============================================
Sends an itemized daily expense summary and audit report with an attached CSV
spreadsheet to the email address specified in Company Settings (expense_report_email,
with fallback to admin_backup_email).

Scheduled daily at 04:00 AM IST via users/scheduler.py (APScheduler).

Usage:
    python manage.py send_daily_expense_report
    python manage.py send_daily_expense_report --date 2026-11-06
    python manage.py send_daily_expense_report --email accounts@odtechsolutions.com
"""

import io
import csv
import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from django.db.models import Sum, Count, Q

from config.models import CompanyProfile
from payments.models import Expense


class Command(BaseCommand):
    help = "Send daily expense entries report to the email configured in Company Settings (runs at 4:00 AM IST)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            default=None,
            help='Target date in YYYY-MM-DD format (defaults to yesterday, the full completed day of expense submissions)',
        )
        parser.add_argument(
            '--email',
            type=str,
            default=None,
            help='Override recipient email address (defaults to Company Settings: expense_report_email or admin_backup_email)',
        )
        parser.add_argument(
            '--include-all',
            action='store_true',
            default=False,
            help='Include all expenses if target date has zero entries',
        )

    def handle(self, *args, **options):
        now = timezone.localtime()
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] Starting Daily Expense Report generation..."
        ))

        # ── 1. Determine Recipient Email ───────────────────────────────────────────
        recipient_email = options.get('email')
        profile = CompanyProfile.objects.first()

        if not recipient_email and profile:
            recipient_email = (profile.expense_report_email or profile.admin_backup_email or '').strip()

        if not recipient_email:
            msg = (
                "No recipient email found! Please specify 'Daily Expense Report Email' or "
                "'Admin Backup Email' in Company Settings (/config/settings/) or pass --email."
            )
            self.stderr.write(self.style.ERROR(f"  [ERROR] {msg}"))
            return

        self.stdout.write(f"  Recipient Email: {recipient_email}")

        # ── 2. Determine Target Date Range ─────────────────────────────────────────
        date_str = options.get('date')
        if date_str:
            try:
                target_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                self.stderr.write(self.style.ERROR(f"  [ERROR] Invalid date format '{date_str}'. Use YYYY-MM-DD."))
                return
        else:
            # When running at 04:00 AM, yesterday represents the full completed business day
            target_date = now.date() - datetime.timedelta(days=1)

        self.stdout.write(f"  Target Report Date: {target_date.strftime('%d %B %Y')}")

        # ── 3. Query Expenses for Target Date ───────────────────────────────────────
        expenses_qs = Expense.objects.select_related('submitted_by', 'approved_by').filter(date=target_date).order_by('-id')
        
        # If no expenses on target date and --include-all specified, fallback to last 7 days
        include_all = options.get('include_all', False)
        if not expenses_qs.exists() and include_all:
            self.stdout.write(self.style.WARNING(f"  No expenses found for {target_date}. Including recent expenses..."))
            expenses_qs = Expense.objects.select_related('submitted_by', 'approved_by').all().order_by('-date', '-id')[:50]

        expenses_list = list(expenses_qs)
        total_count = len(expenses_list)

        # Totals calculation
        total_ex_gst = Decimal('0.00')
        total_gst = Decimal('0.00')
        total_amount = Decimal('0.00')
        approved_count = 0
        approved_amount = Decimal('0.00')

        # Category mapping for breakdown
        category_map = {}

        for exp in expenses_list:
            amt = exp.amount or Decimal('0.00')
            gst = exp.gst_amount or Decimal('0.00')
            gross = amt + gst

            total_ex_gst += amt
            total_gst += gst
            total_amount += gross

            if exp.status == 'Approved':
                approved_count += 1
                approved_amount += gross

            cat = exp.expense_type or 'Other'
            if cat not in category_map:
                category_map[cat] = {'category': cat, 'count': 0, 'amount': Decimal('0.00')}
            category_map[cat]['count'] += 1
            category_map[cat]['amount'] += gross

        # Build sorted category breakdown
        category_summary = []
        for cat_data in sorted(category_map.values(), key=lambda x: x['amount'], reverse=True):
            pct = round((cat_data['amount'] / total_amount * 100), 1) if total_amount > 0 else 0
            cat_data['percentage'] = pct
            category_summary.append(cat_data)

        # ── 4. Query All Action Pending Expenses ────────────────────────────────────
        pending_qs = Expense.objects.filter(status__in=['Pending', 'Clarification', 'Clarification Provided'])
        pending_count = pending_qs.count()
        pending_amount_data = pending_qs.aggregate(total=Sum('amount'), gst=Sum('gst_amount'))
        pending_amount = (pending_amount_data['total'] or Decimal('0.00')) + (pending_amount_data['gst'] or Decimal('0.00'))

        # ── 5. Query Month-to-Date (MTD) Totals ─────────────────────────────────────
        first_day_of_month = target_date.replace(day=1)
        mtd_qs = Expense.objects.filter(date__gte=first_day_of_month, date__lte=target_date)
        mtd_total_count = mtd_qs.count()
        mtd_data = mtd_qs.aggregate(total=Sum('amount'), gst=Sum('gst_amount'))
        mtd_total_amount = (mtd_data['total'] or Decimal('0.00')) + (mtd_data['gst'] or Decimal('0.00'))
        mtd_month_name = target_date.strftime('%B %Y')

        self.stdout.write(f"  Summary: {total_count} entries for {target_date} (Total: Rs. {total_amount:,.2f})")
        self.stdout.write(f"  Action Pending in System: {pending_count} entries (Total: Rs. {pending_amount:,.2f})")
        self.stdout.write(f"  MTD ({mtd_month_name}): {mtd_total_count} entries (Total: Rs. {mtd_total_amount:,.2f})")

        # ── 6. Generate CSV Attachment ──────────────────────────────────────────────
        csv_buffer = io.StringIO()
        csv_writer = csv.writer(csv_buffer)
        
        # CSV Header
        csv_writer.writerow([
            'Expense ID',
            'Date',
            'Employee Code',
            'Submitted By',
            'Category',
            'Description / Title',
            'Amount Excl GST (INR)',
            'GST Amount (INR)',
            'Total Amount (INR)',
            'Status',
            'Payment Status',
            'Paid At',
            'Approved By',
            'Approved At',
            'Notes',
        ])

        # CSV Data Rows
        # If there are expenses on target date, export them. If none on target date, export recent MTD entries
        export_qs = expenses_qs if expenses_qs.exists() else mtd_qs.order_by('-date', '-id')
        for exp in export_qs:
            gross = (exp.amount or Decimal('0.00')) + (exp.gst_amount or Decimal('0.00'))
            submitted_name = exp.submitted_by.get_full_name() or exp.submitted_by.username if exp.submitted_by else ''
            approved_name = exp.approved_by.get_full_name() or exp.approved_by.username if exp.approved_by else ''
            
            csv_writer.writerow([
                exp.expense_id,
                exp.date.strftime('%Y-%m-%d') if exp.date else '',
                exp.employee_code or '',
                submitted_name,
                exp.expense_type or '',
                exp.title or '',
                f"{(exp.amount or 0):.2f}",
                f"{(exp.gst_amount or 0):.2f}",
                f"{gross:.2f}",
                exp.status or '',
                'Paid' if exp.is_paid else 'Unpaid',
                exp.paid_at.strftime('%Y-%m-%d %H:%M') if exp.paid_at else '',
                approved_name,
                exp.approved_at.strftime('%Y-%m-%d %H:%M') if exp.approved_at else '',
                exp.notes or '',
            ])

        csv_content = csv_buffer.getvalue()
        csv_buffer.close()

        # ── 7. Render HTML & Text Email ─────────────────────────────────────────────
        company_name = profile.name if profile and profile.name else "ODtech Solutions"
        report_date_str = target_date.strftime('%d %B %Y')
        report_date_slug = target_date.strftime('%Y-%m-%d')

        context = {
            'company_name': company_name,
            'report_date': report_date_str,
            'report_date_slug': report_date_slug,
            'expenses': expenses_list,
            'total_count': total_count,
            'total_amount': total_amount,
            'total_ex_gst': total_ex_gst,
            'total_gst': total_gst,
            'approved_count': approved_count,
            'approved_amount': approved_amount,
            'pending_count': pending_count,
            'pending_amount': pending_amount,
            'category_summary': category_summary,
            'mtd_month_name': mtd_month_name,
            'mtd_total_count': mtd_total_count,
            'mtd_total_amount': mtd_total_amount,
            'portal_url': 'http://192.168.1.106:8000/payments/expenses/',
        }

        html_content = render_to_string('payments/daily_expense_report_email.html', context)
        import re
        clean_html = re.sub(r'(?is)<style.*?>.*?</style>', '', html_content)
        text_content = strip_tags(clean_html)

        subject = f"[{company_name}] Daily Expense Report - {report_date_str} (Rs. {total_amount:,.2f})"

        # ── 8. Dispatch Email with CSV Attachment ────────────────────────────────────
        try:
            email_msg = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=None,
                to=[recipient_email],
            )
            email_msg.attach_alternative(html_content, "text/html")
            
            # Attach CSV
            filename = f"Expense_Report_{report_date_slug}.csv"
            email_msg.attach(filename, csv_content, 'text/csv')

            email_msg.send(fail_silently=False)
            self.stdout.write(self.style.SUCCESS(
                f"  [SUCCESS] Daily Expense Report successfully sent to {recipient_email} (Attached: {filename})."
            ))
        except Exception as exc:
            self.stderr.write(self.style.ERROR(
                f"  [FAIL] Failed to send email to {recipient_email}: {exc}"
            ))
            raise
