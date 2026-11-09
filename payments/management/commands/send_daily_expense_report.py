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
            help='(Deprecated) Only that day expenses are sent',
        )
        parser.add_argument(
            '--skip-users',
            action='store_true',
            default=False,
            help='Skip sending consolidated user digests (send only company admin report)',
        )
        parser.add_argument(
            '--skip-admin',
            action='store_true',
            default=False,
            help='Skip sending company admin report (send only consolidated user digests)',
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

        # ── 3. Query Expenses for Target Date ONLY ─────────────────────────────────
        # Strictly include only expenses for this specific date (no historical entries)
        day_q = Q(date=target_date) | Q(created_at__date=target_date)
        expenses_qs = Expense.objects.select_related('submitted_by', 'approved_by').filter(day_q).distinct().order_by('-id')

        expenses_list = list(expenses_qs)
        total_count = len(expenses_list)

        # Totals calculation strictly for that day
        total_ex_gst = Decimal('0.00')
        total_gst = Decimal('0.00')
        total_amount = Decimal('0.00')
        approved_count = 0
        approved_amount = Decimal('0.00')
        pending_count = 0
        pending_amount = Decimal('0.00')

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
            elif exp.status in ['Pending', 'Clarification', 'Clarification Provided']:
                pending_count += 1
                pending_amount += gross

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

        self.stdout.write(f"  Summary for {target_date}: {total_count} entries (Total: Rs. {total_amount:,.2f})")
        self.stdout.write(f"  Approved: {approved_count} (Rs. {approved_amount:,.2f}) | Pending: {pending_count} (Rs. {pending_amount:,.2f})")

        # ── 6. Render HTML & Text Email ─────────────────────────────────────────────
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
            'portal_url': 'http://192.168.1.106:8000/payments/expenses/',
        }

        html_content = render_to_string('payments/daily_expense_report_email.html', context)
        import re
        clean_html = re.sub(r'(?is)<style.*?>.*?</style>', '', html_content)
        text_content = strip_tags(clean_html)

        subject = f"[{company_name}] Daily Expense Report - {report_date_str} (Rs. {total_amount:,.2f})"

        # ── 7. Dispatch Email Directly as HTML/CSS Page (No CSV/Excel attachment) ───
        skip_admin = options.get('skip_admin', False)
        if not skip_admin:
            try:
                email_msg = EmailMultiAlternatives(
                    subject=subject,
                    body=text_content,
                    from_email=None,
                    to=[recipient_email],
                )
                email_msg.attach_alternative(html_content, "text/html")
                email_msg.send(fail_silently=False)
                self.stdout.write(self.style.SUCCESS(
                    f"  [SUCCESS] Daily Expense Report email successfully sent to {recipient_email} as formatted HTML/CSS page."
                ))
            except Exception as exc:
                self.stderr.write(self.style.ERROR(
                    f"  [FAIL] Failed to send email to {recipient_email}: {exc}"
                ))
                raise

        # ── 8. Dispatch Consolidated Daily Digest to Employees/Users ──────────────────
        mode = getattr(profile, 'expense_email_mode', 'DAILY_DIGEST')
        skip_users = options.get('skip_users', False)
        if mode != 'OFF' and not skip_users:
            self.stdout.write("  Preparing consolidated user daily expense digests (4:00 AM)...")
            user_activity_q = (
                Q(date=target_date) |
                Q(created_at__date=target_date) |
                Q(approved_at__date=target_date) |
                Q(paid_at__date=target_date) |
                Q(clarification_raised_at__date=target_date)
            )

            activity_expenses = Expense.objects.select_related('submitted_by', 'approved_by').filter(user_activity_q).distinct()
            
            # Group by user (submitted_by)
            user_map = {}
            for exp in activity_expenses:
                u = exp.submitted_by
                if u and u.email and '@' in u.email:
                    user_map.setdefault(u, []).append(exp)

            user_digest_count = 0
            for user_obj, user_exp_list in user_map.items():
                try:
                    u_total = sum((e.amount or Decimal('0.00')) + (e.gst_amount or Decimal('0.00')) for e in user_exp_list)
                    u_approved = sum((e.amount or Decimal('0.00')) + (e.gst_amount or Decimal('0.00')) for e in user_exp_list if e.status == 'Approved')
                    u_paid = sum((e.amount or Decimal('0.00')) + (e.gst_amount or Decimal('0.00')) for e in user_exp_list if e.is_paid)
                    has_clarification = any(e.status in ['Clarification', 'Clarification Provided'] for e in user_exp_list)

                    u_context = {
                        'company_name': company_name,
                        'recipient_name': user_obj.get_full_name() or user_obj.username,
                        'report_date': report_date_str,
                        'expenses': user_exp_list,
                        'total_amount': u_total,
                        'approved_amount': u_approved,
                        'paid_amount': u_paid,
                        'has_clarification': has_clarification,
                        'portal_url': 'http://192.168.1.106:8000/payments/expenses/',
                    }

                    u_html = render_to_string('payments/user_daily_expense_digest_email.html', u_context)
                    u_clean = re.sub(r'(?is)<style.*?>.*?</style>', '', u_html)
                    u_text = strip_tags(u_clean)

                    u_subject = f"[{company_name}] Your Daily Expenses Digest - {report_date_str} ({len(user_exp_list)} entries)"

                    u_msg = EmailMultiAlternatives(
                        subject=u_subject,
                        body=u_text,
                        from_email=None,
                        to=[user_obj.email],
                    )
                    u_msg.attach_alternative(u_html, "text/html")
                    u_msg.send(fail_silently=False)
                    user_digest_count += 1
                    self.stdout.write(f"    [OK] Sent single consolidated digest to {user_obj.email} ({len(user_exp_list)} entries)")
                except Exception as ex:
                    self.stderr.write(f"    [WARN] Failed sending digest to {user_obj.email}: {ex}")

            self.stdout.write(self.style.SUCCESS(f"  Dispatched {user_digest_count} consolidated user digest email(s)."))

