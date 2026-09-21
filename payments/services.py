import logging
import threading
from django.db.models import Sum
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.contrib.auth import get_user_model
from django.utils.html import strip_tags
from .models import Payment

logger = logging.getLogger(__name__)
User = get_user_model()


class CustomerLedgerService:
    @staticmethod
    def get_outstanding_balance(contact_id):
        """Return total payments made by a contact (billing documents removed)."""
        payments_total = Payment.objects.filter(
            contact_id=contact_id
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        return payments_total


class ExpenseNotificationService:
    """Handles background email dispatch and in-app notifications for Expense clarification and approval events."""

    @staticmethod
    def _send_email_async(subject, recipient_emails, html_content):
        def _send():
            try:
                from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', '') or getattr(settings, 'EMAIL_HOST_USER', '') or 'noreply@odtech.in'
                text_content = strip_tags(html_content)
                for email in recipient_emails:
                    email = (email or '').strip()
                    if not email or '@' not in email:
                        continue
                    msg = EmailMultiAlternatives(subject, text_content, from_email, [email])
                    msg.attach_alternative(html_content, "text/html")
                    msg.send(fail_silently=False)
                    logger.info(f"[Expense Email] Sent '{subject}' to {email}")
            except Exception as e:
                logger.error(f"[Expense Email Error] Failed sending '{subject}' to {recipient_emails}: {e}")

        t = threading.Thread(target=_send, daemon=True)
        t.start()

    @classmethod
    def notify_clarification_raised(cls, expense, admin_user, request=None):
        """Notify the uploaded user that admin has requested clarification before approval."""
        try:
            from tracker.models import Notification
        except Exception:
            Notification = None

        base_url = request.build_absolute_uri('/')[:-1] if request else getattr(settings, 'SITE_URL', 'http://localhost:8000')
        edit_url = f"{base_url}/payments/expenses/{expense.id}/edit/"

        recipients = []
        user = expense.submitted_by
        if user:
            recipients.append(user)
        emp_user = getattr(expense, 'employee_user', None)
        if emp_user and emp_user != user and emp_user not in recipients:
            recipients.append(emp_user)

        # 1. In-app Notification
        if Notification:
            for r in recipients:
                try:
                    Notification.objects.create(
                        user=r,
                        title=f"Clarification Needed: {expense.expense_id}",
                        message=f"Admin {admin_user.get_full_name() or admin_user.username} requested clarification: {expense.clarification_query}",
                        link=f"/payments/expenses/{expense.id}/edit/",
                    )
                except Exception as ex:
                    logger.warning(f"Could not create in-app notification: {ex}")

        # 2. Email Notification
        email_addrs = [r.email for r in recipients if r and r.email]
        if not email_addrs:
            return

        subject = f"[ODtech ERP] Action Required: Clarification Requested for Expense {expense.expense_id}"
        html_content = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden;">
            <div style="background: #f59e0b; padding: 20px; color: #ffffff; text-align: center;">
                <h2 style="margin: 0; font-size: 20px;">Clarification Requested on Expense</h2>
                <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.9;">Action required before expense approval</p>
            </div>
            <div style="padding: 24px; color: #334155; line-height: 1.6;">
                <p style="font-size: 15px;">Hello <strong>{user.get_full_name() or user.username}</strong>,</p>
                <p>Admin <strong>{admin_user.get_full_name() or admin_user.username}</strong> has requested additional information or corrections on your expense submission:</p>
                
                <div style="background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #f59e0b; border-radius: 8px; padding: 14px 18px; margin: 18px 0;">
                    <div style="font-size: 11px; font-weight: bold; color: #b45309; text-transform: uppercase; margin-bottom: 4px;">Admin Query:</div>
                    <div style="font-size: 14px; color: #78350f; font-weight: 500;">{expense.clarification_query}</div>
                </div>

                <table style="width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px;">
                    <tr style="border-bottom: 1px solid #f1f5f9;">
                        <td style="padding: 8px 0; color: #64748b;">Expense ID</td>
                        <td style="padding: 8px 0; font-weight: 600; text-align: right; font-family: monospace;">{expense.expense_id}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f1f5f9;">
                        <td style="padding: 8px 0; color: #64748b;">Title / Purpose</td>
                        <td style="padding: 8px 0; font-weight: 600; text-align: right;">{expense.title}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f1f5f9;">
                        <td style="padding: 8px 0; color: #64748b;">Category</td>
                        <td style="padding: 8px 0; font-weight: 600; text-align: right;">{expense.expense_type}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f1f5f9;">
                        <td style="padding: 8px 0; color: #64748b;">Amount</td>
                        <td style="padding: 8px 0; font-weight: bold; text-align: right; color: #2563eb;">₹{expense.amount}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b;">Date</td>
                        <td style="padding: 8px 0; font-weight: 600; text-align: right;">{expense.date.strftime('%d %b %Y') if expense.date else ''}</td>
                    </tr>
                </table>

                <div style="text-align: center; margin: 28px 0 16px 0;">
                    <a href="{edit_url}" style="background: #2563eb; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: 600; font-size: 14px; display: inline-block;">
                        Review & Update Expense →
                    </a>
                </div>
                <p style="font-size: 12px; color: #94a3b8; text-align: center;">Please update your expense with the requested details so Admin can approve it.</p>
            </div>
            <div style="background: #f8fafc; border-top: 1px solid #f1f5f9; padding: 12px; text-align: center; font-size: 11px; color: #94a3b8;">
                ODtech Solutions ERP • Automated Notification
            </div>
        </div>
        """
        cls._send_email_async(subject, email_addrs, html_content)

    @classmethod
    def notify_clarification_submitted(cls, expense, submitter_user, request=None):
        """Notify the Admin who raised clarification that the user has provided the required explanation."""
        try:
            from tracker.models import Notification
        except Exception:
            Notification = None

        base_url = request.build_absolute_uri('/')[:-1] if request else getattr(settings, 'SITE_URL', 'http://localhost:8000')
        detail_url = f"{base_url}/payments/expenses/{expense.id}/"

        admin_recipients = []
        if expense.clarification_raised_by and expense.clarification_raised_by.is_active:
            admin_recipients.append(expense.clarification_raised_by)
        else:
            # Fallback: find all superusers or admin role users
            admin_recipients = list(User.objects.filter(is_active=True, is_superuser=True))

        # 1. In-app Notification
        if Notification:
            for admin in admin_recipients:
                try:
                    Notification.objects.create(
                        user=admin,
                        title=f"Clarification Provided: {expense.expense_id}",
                        message=f"{submitter_user.get_full_name() or submitter_user.username} provided clarification on '{expense.title}'. Ready for review.",
                        link=f"/payments/expenses/{expense.id}/",
                    )
                except Exception as ex:
                    logger.warning(f"Could not create in-app notification: {ex}")

        # 2. Email Notification
        email_addrs = [admin.email for admin in admin_recipients if admin and admin.email]
        if not email_addrs:
            return

        subject = f"[ODtech ERP] Clarification Provided for Expense {expense.expense_id} - {expense.title}"
        html_content = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden;">
            <div style="background: #2563eb; padding: 20px; color: #ffffff; text-align: center;">
                <h2 style="margin: 0; font-size: 20px;">Clarification Provided by Employee</h2>
                <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.9;">Ready for Admin Approval</p>
            </div>
            <div style="padding: 24px; color: #334155; line-height: 1.6;">
                <p style="font-size: 15px;">Hello Admin,</p>
                <p>Employee <strong>{submitter_user.get_full_name() or submitter_user.username}</strong> has updated their expense and submitted the requested clarification:</p>
                
                <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-left: 4px solid #2563eb; border-radius: 8px; padding: 14px 18px; margin: 18px 0;">
                    <div style="font-size: 11px; font-weight: bold; color: #1e40af; text-transform: uppercase; margin-bottom: 4px;">User's Clarification Response:</div>
                    <div style="font-size: 14px; color: #1e3a8a; font-weight: 500;">{expense.clarification_response}</div>
                </div>

                <table style="width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px;">
                    <tr style="border-bottom: 1px solid #f1f5f9;">
                        <td style="padding: 8px 0; color: #64748b;">Expense ID</td>
                        <td style="padding: 8px 0; font-weight: 600; text-align: right; font-family: monospace;">{expense.expense_id}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f1f5f9;">
                        <td style="padding: 8px 0; color: #64748b;">Title / Purpose</td>
                        <td style="padding: 8px 0; font-weight: 600; text-align: right;">{expense.title}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f1f5f9;">
                        <td style="padding: 8px 0; color: #64748b;">Amount</td>
                        <td style="padding: 8px 0; font-weight: bold; text-align: right; color: #059669;">₹{expense.amount}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b;">Status</td>
                        <td style="padding: 8px 0; font-weight: 600; text-align: right; color: #2563eb;">Clarification Provided</td>
                    </tr>
                </table>

                <div style="text-align: center; margin: 28px 0 16px 0;">
                    <a href="{detail_url}" style="background: #059669; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: 600; font-size: 14px; display: inline-block;">
                        Review & Approve Expense →
                    </a>
                </div>
            </div>
            <div style="background: #f8fafc; border-top: 1px solid #f1f5f9; padding: 12px; text-align: center; font-size: 11px; color: #94a3b8;">
                ODtech Solutions ERP • Automated Notification
            </div>
        </div>
        """
        cls._send_email_async(subject, email_addrs, html_content)

    @classmethod
    def notify_expense_approved(cls, expense, approver_user, request=None):
        """Notify the uploaded user that their expense has been approved."""
        try:
            from tracker.models import Notification
        except Exception:
            Notification = None

        base_url = request.build_absolute_uri('/')[:-1] if request else getattr(settings, 'SITE_URL', 'http://localhost:8000')
        detail_url = f"{base_url}/payments/expenses/{expense.id}/"

        recipients = []
        user = expense.submitted_by
        if user:
            recipients.append(user)
        emp_user = getattr(expense, 'employee_user', None)
        if emp_user and emp_user != user and emp_user not in recipients:
            recipients.append(emp_user)

        # 1. In-app Notification
        if Notification:
            for r in recipients:
                try:
                    Notification.objects.create(
                        user=r,
                        title=f"Expense Approved: {expense.expense_id}",
                        message=f"Your expense '{expense.title}' for ₹{expense.amount} has been approved by {approver_user.get_full_name() or approver_user.username}.",
                        link=f"/payments/expenses/{expense.id}/",
                    )
                except Exception as ex:
                    logger.warning(f"Could not create in-app notification: {ex}")

        # 2. Email Notification
        email_addrs = [r.email for r in recipients if r and r.email]
        if not email_addrs:
            return

        subject = f"[ODtech ERP] Expense Approved: {expense.expense_id} - {expense.title}"
        html_content = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden;">
            <div style="background: #059669; padding: 20px; color: #ffffff; text-align: center;">
                <h2 style="margin: 0; font-size: 20px;">Expense Approved</h2>
                <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.9;">Official Expense Approval Confirmation</p>
            </div>
            <div style="padding: 24px; color: #334155; line-height: 1.6;">
                <p style="font-size: 15px;">Hello <strong>{user.get_full_name() or user.username}</strong>,</p>
                <p>Great news! Your expense has been reviewed and <strong>Approved</strong> by <strong>{approver_user.get_full_name() or approver_user.username}</strong>.</p>

                <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 14px 18px; margin: 18px 0; text-align: center;">
                    <div style="font-size: 12px; color: #166534; font-weight: 600; text-transform: uppercase;">Approved Amount</div>
                    <div style="font-size: 26px; color: #15803d; font-weight: bold; margin-top: 4px;">₹{expense.amount}</div>
                </div>

                <table style="width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px;">
                    <tr style="border-bottom: 1px solid #f1f5f9;">
                        <td style="padding: 8px 0; color: #64748b;">Expense ID</td>
                        <td style="padding: 8px 0; font-weight: 600; text-align: right; font-family: monospace;">{expense.expense_id}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f1f5f9;">
                        <td style="padding: 8px 0; color: #64748b;">Title / Purpose</td>
                        <td style="padding: 8px 0; font-weight: 600; text-align: right;">{expense.title}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f1f5f9;">
                        <td style="padding: 8px 0; color: #64748b;">Category</td>
                        <td style="padding: 8px 0; font-weight: 600; text-align: right;">{expense.expense_type}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #64748b;">Date</td>
                        <td style="padding: 8px 0; font-weight: 600; text-align: right;">{expense.date.strftime('%d %b %Y') if expense.date else ''}</td>
                    </tr>
                </table>

                <div style="text-align: center; margin: 28px 0 16px 0;">
                    <a href="{detail_url}" style="background: #059669; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: 600; font-size: 14px; display: inline-block;">
                        View Expense Details →
                    </a>
                </div>
            </div>
            <div style="background: #f8fafc; border-top: 1px solid #f1f5f9; padding: 12px; text-align: center; font-size: 11px; color: #94a3b8;">
                ODtech Solutions ERP • Automated Notification
            </div>
        </div>
        """
        cls._send_email_async(subject, email_addrs, html_content)

