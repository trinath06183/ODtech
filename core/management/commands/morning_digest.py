"""
Management Command: morning_digest
====================================
Sends a daily executive morning digest email to the admin with key business KPIs:
  - Revenue today / MTD / YTD
  - Orders by status
  - Payments received today
  - Pending expense approvals
  - Overdue invoices count

Scheduled by APScheduler daily at 09:00 AM IST via users/scheduler.py.
Run manually: python manage.py morning_digest
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand
from django.db.models import Sum, Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Send daily executive morning digest email to the admin."

    def handle(self, *args, **options):
        self.stdout.write("morning_digest: Building digest...")

        # ── Resolve admin email ───────────────────────────────────────────────
        try:
            from config.models import CompanyProfile
            profile = CompanyProfile.objects.first()
            admin_email = profile.admin_backup_email if profile and profile.admin_backup_email else None
            company_name = profile.name if profile else "ODtech ERP"
        except Exception:
            admin_email = None
            company_name = "ODtech ERP"

        if not admin_email:
            admin_email = getattr(settings, 'EDMS_MD_EMAIL', None) or settings.EMAIL_HOST_USER

        if not admin_email:
            self.stderr.write("morning_digest: No admin email configured. Skipping.")
            return

        Z = Decimal('0')
        today = date.today()
        mtd_start = today.replace(day=1)
        fy_y = today.year if today.month >= 4 else today.year - 1
        ytd_start = date(fy_y, 4, 1)

        # ── 1. Revenue ────────────────────────────────────────────────────────
        from documents.models import Document
        rev_today = Document.objects.filter(
            type='INV', status='Approved', date=today
        ).aggregate(t=Sum('grand_total'))['t'] or Z

        rev_mtd = Document.objects.filter(
            type='INV', status='Approved', date__gte=mtd_start, date__lte=today
        ).aggregate(t=Sum('grand_total'))['t'] or Z

        rev_ytd = Document.objects.filter(
            type='INV', status='Approved', date__gte=ytd_start, date__lte=today
        ).aggregate(t=Sum('grand_total'))['t'] or Z

        inv_today_count = Document.objects.filter(type='INV', date=today).count()

        # ── 2. Quotations ─────────────────────────────────────────────────────
        qtn_today = Document.objects.filter(type='QTN', date=today).count()
        qtn_week_start = today - timedelta(days=today.weekday())
        qtn_this_week = Document.objects.filter(type='QTN', date__gte=qtn_week_start).count()

        # ── 3. Orders by status ───────────────────────────────────────────────
        order_summary = {}
        new_orders_today = 0
        try:
            from tracker.models import Order
            orders_qs = Order.objects.all()
            new_orders_today = Order.objects.filter(order_date=today).count()
            for status, label in Order.STATUS_CHOICES:
                order_summary[label] = orders_qs.filter(order_status=status).count()
        except Exception:
            pass

        # ── 4. Payments received today ────────────────────────────────────────
        payments_today = Z
        payments_count_today = 0
        try:
            from payments.models import Payment
            p_qs = Payment.objects.filter(date=today)
            payments_today = p_qs.aggregate(t=Sum('amount'))['t'] or Z
            payments_count_today = p_qs.count()
        except Exception:
            pass

        # ── 5. Pending expense approvals ──────────────────────────────────────
        pending_exp_count = 0
        pending_exp_amount = Z
        try:
            from payments.models import Expense
            exp_qs = Expense.objects.filter(status='Pending')
            pending_exp_count = exp_qs.count()
            pending_exp_amount = exp_qs.aggregate(t=Sum('amount'))['t'] or Z
        except Exception:
            pass

        # ── 6. Overdue invoices (>30 days) ────────────────────────────────────
        overdue_count = 0
        try:
            overdue_count = Document.objects.filter(
                type='INV', status='Approved',
                date__lt=today - timedelta(days=30)
            ).count()
        except Exception:
            pass

        # ── Build email ────────────────────────────────────────────────────────
        now_str = timezone.now().strftime('%A, %d %B %Y, %I:%M %p IST')
        date_str = today.strftime('%d %b %Y')

        def fmt(v):
            return f"Rs.{float(v):,.2f}"

        text_body = f"""Good morning!

Here is your daily executive digest for {date_str}.
Generated at: {now_str}

REVENUE SUMMARY
  Today's Invoiced Revenue : {fmt(rev_today)}  ({inv_today_count} invoices)
  Month-to-Date (MTD)      : {fmt(rev_mtd)}
  Financial Year-to-Date   : {fmt(rev_ytd)}

ORDERS & QUOTATIONS
  New Orders Today          : {new_orders_today}
  Quotations Today          : {qtn_today}
  Quotations This Week      : {qtn_this_week}

  Order Pipeline:
"""
        for label, count in order_summary.items():
            text_body += f"    {label:<20}: {count}\n"

        text_body += f"""
CASH & PAYMENTS
  Payments Received Today   : {fmt(payments_today)}  ({payments_count_today} transactions)
  Pending Expense Approvals : {pending_exp_count} claims worth {fmt(pending_exp_amount)}

ALERTS
  Overdue Invoices (>30 days) : {overdue_count} invoice(s)

Have a productive day!

-- {company_name} (Automated Morning Digest)
"""

        # Rich HTML version
        order_rows_html = "\n".join(
            f"<tr><td style='padding:6px 12px;color:#94a3b8;font-size:13px;'>{lbl}</td>"
            f"<td style='padding:6px 12px;font-weight:700;color:#f8fafc;font-size:13px;'>{cnt}</td></tr>"
            for lbl, cnt in order_summary.items()
        )

        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0f172a;font-family:'Segoe UI',Arial,sans-serif;color:#e2e8f0;">
<div style="max-width:600px;margin:32px auto;border-radius:16px;overflow:hidden;border:1px solid #1e293b;">
  <div style="background:linear-gradient(135deg,#1e3a5f,#1e293b);padding:32px 32px 24px;">
    <div style="font-size:26px;font-weight:800;color:#f8fafc;">Morning Digest</div>
    <div style="font-size:13px;color:#64748b;margin-top:6px;">{now_str}</div>
  </div>

  <div style="padding:24px 32px;background:#111827;border-bottom:1px solid #1e293b;">
    <div style="font-size:12px;font-weight:700;letter-spacing:1px;color:#6366f1;margin-bottom:16px;text-transform:uppercase;">Revenue</div>
    <table width="100%" cellspacing="0">
      <tr>
        <td style="text-align:center;padding:12px;">
          <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:1px;">Today</div>
          <div style="font-size:22px;font-weight:800;color:#10b981;">Rs. {float(rev_today):,.0f}</div>
          <div style="font-size:11px;color:#475569;">{inv_today_count} invoices</div>
        </td>
        <td style="text-align:center;padding:12px;border-left:1px solid #1e293b;">
          <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:1px;">MTD</div>
          <div style="font-size:22px;font-weight:800;color:#f8fafc;">Rs. {float(rev_mtd):,.0f}</div>
        </td>
        <td style="text-align:center;padding:12px;border-left:1px solid #1e293b;">
          <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:1px;">FY-to-Date</div>
          <div style="font-size:22px;font-weight:800;color:#f8fafc;">Rs. {float(rev_ytd):,.0f}</div>
        </td>
      </tr>
    </table>
  </div>

  <div style="padding:24px 32px;background:#0f172a;border-bottom:1px solid #1e293b;">
    <div style="font-size:12px;font-weight:700;letter-spacing:1px;color:#f59e0b;margin-bottom:12px;text-transform:uppercase;">Order Pipeline</div>
    <div style="margin-bottom:12px;font-size:13px;color:#94a3b8;">New today: <b style="color:#f8fafc;">{new_orders_today}</b> &nbsp;|&nbsp; Quotations today: <b style="color:#f8fafc;">{qtn_today}</b></div>
    <table width="100%" cellspacing="0" style="border-radius:8px;overflow:hidden;">
      <tr style="background:#1e293b;">
        <th style="padding:8px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase;">Status</th>
        <th style="padding:8px 12px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase;">Orders</th>
      </tr>
      {order_rows_html}
    </table>
  </div>

  <div style="padding:24px 32px;background:#111827;border-bottom:1px solid #1e293b;">
    <div style="font-size:12px;font-weight:700;letter-spacing:1px;color:#10b981;margin-bottom:12px;text-transform:uppercase;">Cash & Payments</div>
    <div style="font-size:14px;margin-bottom:8px;color:#e2e8f0;">Received Today: <b style="color:#10b981;">Rs. {float(payments_today):,.2f}</b> ({payments_count_today} transactions)</div>
    <div style="font-size:14px;color:#e2e8f0;">Pending Expenses: <b style="color:#f59e0b;">{pending_exp_count}</b> claims &mdash; Rs. {float(pending_exp_amount):,.2f}</div>
  </div>

  <div style="padding:20px 32px;background:#111827;border-bottom:1px solid #1e293b;">
    <div style="font-size:12px;font-weight:700;letter-spacing:1px;color:#ef4444;margin-bottom:10px;text-transform:uppercase;">Alerts</div>
    <div style="font-size:14px;color:#e2e8f0;">Overdue Invoices (&gt;30 days): <b style="color:{'#ef4444' if overdue_count > 0 else '#10b981'};">{overdue_count}</b></div>
  </div>

  <div style="padding:20px 32px;background:#0f172a;text-align:center;color:#334155;font-size:12px;">
    {company_name} &bull; Automated Morning Digest &bull; Sent at 09:00 AM IST daily
  </div>
</div>
</body>
</html>"""

        subject = f"[{company_name}] Morning Digest - {date_str}"

        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[admin_email],
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send(fail_silently=False)
            logger.info("morning_digest: Digest sent to %s", admin_email)
            self.stdout.write(self.style.SUCCESS(
                f"morning_digest: Digest sent to {admin_email}."
            ))
        except Exception as e:
            logger.error("morning_digest: Failed to send: %s", e, exc_info=True)
            self.stderr.write(f"morning_digest: ERROR: {e}")
