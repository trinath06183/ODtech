from django.shortcuts import render
from django.db.models import Sum, Q, Count
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal

from core.decorators import login_required
from inventory.models import Product
from documents.models import Document
from payments.models import Payment, Expense


@login_required
def gst_report(request):
    """GST Report — billing module has been migrated to EDMS."""
    return render(request, 'reporting/gst_report.html', {
        'rows': [],
        'total_taxable': 0,
        'total_cgst': 0,
        'total_sgst': 0,
        'total_igst': 0,
        'total_grand': 0,
        'fy_options': [],
        'selected_fy': '',
        'selected_month': '',
        'notice': 'Billing documents have been migrated to the EDMS module.',
    })


@login_required
def stock_summary(request):
    products = Product.objects.all().order_by('name')
    rows = []
    total_value = 0
    for p in products:
        stock = p.current_stock
        value = float(stock) * float(p.purchase_price)
        rows.append({
            'product': p,
            'stock': stock,
            'value': value,
        })
        total_value += value

    return render(request, 'reporting/stock_summary.html', {
        'rows': rows,
        'total_value': total_value,
    })


@login_required
def financial_dashboard(request):
    """Financial & Operational Summary Dashboard with P&L, sales, purchases, expenses, orders & reminders."""
    today = date.today()

    # ── Date filter ────────────────────────────────────────────────────────────
    period = request.GET.get('period', 'this_month')

    if period == 'today':
        start_date = today
        end_date = today
        label = "Today"
    elif period == 'this_week':
        start_date = today - timedelta(days=today.weekday())
        end_date = today
        label = "This Week"
    elif period == 'this_month':
        start_date = today.replace(day=1)
        end_date = today
        label = "This Month"
    elif period == 'last_month':
        first_of_month = today.replace(day=1)
        end_date = first_of_month - timedelta(days=1)
        start_date = end_date.replace(day=1)
        label = "Last Month"
    elif period == 'this_quarter':
        q = (today.month - 1) // 3
        start_date = date(today.year, q * 3 + 1, 1)
        end_date = today
        label = "This Quarter"
    elif period == 'this_fy':
        fy_start_year = today.year if today.month >= 4 else today.year - 1
        start_date = date(fy_start_year, 4, 1)
        end_date = today
        label = f"FY {fy_start_year}-{str(fy_start_year + 1)[2:]}"
    elif period == 'this_year':
        start_date = date(today.year, 1, 1)
        end_date = today
        label = f"Year {today.year}"
    elif period == 'custom':
        try:
            start_date = date.fromisoformat(request.GET.get('start', ''))
            end_date = date.fromisoformat(request.GET.get('end', ''))
            label = f"{start_date.strftime('%d %b %Y')} – {end_date.strftime('%d %b %Y')}"
        except (ValueError, TypeError):
            start_date = today.replace(day=1)
            end_date = today
            label = "This Month"
    else:
        start_date = today.replace(day=1)
        end_date = today
        label = "This Month"

    # ── Approved Documents in period ──────────────────────────────────────────
    docs_qs = Document.objects.filter(
        status='Approved',
        date__gte=start_date,
        date__lte=end_date,
    )

    # Sales = Invoices + Proforma Invoices
    sales_qs = docs_qs.filter(type__in=['INV', 'PRO'])
    total_sales = sales_qs.aggregate(t=Sum('grand_total'))['t'] or Decimal('0')
    total_sales_tax = sales_qs.aggregate(t=Sum('tax_total'))['t'] or Decimal('0')
    total_sales_subtotal = sales_qs.aggregate(t=Sum('subtotal'))['t'] or Decimal('0')
    sales_count = sales_qs.count()

    # Purchase Orders
    po_qs = docs_qs.filter(type='PO')
    total_purchases = po_qs.aggregate(t=Sum('grand_total'))['t'] or Decimal('0')
    purchases_count = po_qs.count()

    # Quotations
    qtn_qs = docs_qs.filter(type='QTN')
    total_quotations = qtn_qs.aggregate(t=Sum('grand_total'))['t'] or Decimal('0')
    quotations_count = qtn_qs.count()

    # Credit Notes / Debit Notes
    credit_notes = docs_qs.filter(type='CRN').aggregate(t=Sum('grand_total'))['t'] or Decimal('0')
    debit_notes = docs_qs.filter(type='DBN').aggregate(t=Sum('grand_total'))['t'] or Decimal('0')

    # ── Payments received in period ───────────────────────────────────────────
    payments_qs = Payment.objects.filter(
        date__gte=start_date,
        date__lte=end_date,
    )
    total_payments_received = payments_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    payments_count = payments_qs.count()

    # ── Expenses & Payments Given in period ────────────────────────────────────
    expenses_qs = Expense.objects.filter(
        date__gte=start_date,
        date__lte=end_date,
        status='Approved',
    )
    total_expenses = expenses_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    total_payments_given = total_expenses
    expenses_count = expenses_qs.count()

    # Outstanding Payables = Pending Expenses + Unpaid Approved Purchase Orders
    pending_expenses = Expense.objects.filter(status='Pending').aggregate(t=Sum('amount'))['t'] or Decimal('0')
    unpaid_pos = Document.objects.filter(type='PO', status='Approved').aggregate(t=Sum('grand_total'))['t'] or Decimal('0')
    amount_needed_to_pay = pending_expenses + (unpaid_pos * Decimal('0.3'))  # Estimated outstanding payables balance

    # Daily expenses vs fixed cost split
    daily_expenses = expenses_qs.filter(
        expense_type__in=['Petrol and Diesel', 'Travel', 'Hotel', 'Food Expenses',
                          'Office stationary', 'Courier expenses', 'Transportation Payment',
                          'Marketing Expenses', 'Customer Delight', 'Other Daily']
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    fixed_expenses = expenses_qs.filter(
        expense_type__in=['Staff salary', 'OFC rent', 'Electricity bill', 'Internet Bill',
                          'Google workspace', 'Website and hosting cost', 'Other Fixed']
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    # ── Order Tracker Metrics ──────────────────────────────────────────────────
    from tracker.models import Order
    orders_qs = Order.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    )
    total_orders = orders_qs.count()
    
    # Status breakdown for Donut Chart
    order_open = orders_qs.filter(order_status='OPEN').count()
    order_in_progress = orders_qs.filter(order_status='IN_PROGRESS').count()
    order_completed = orders_qs.filter(order_status='CLOSED').count()
    order_other = max(0, total_orders - (order_open + order_in_progress + order_completed))

    # ── Profit Calculations ───────────────────────────────────────────────────
    # Gross Profit = Sales Revenue (excluding tax) - Cost of Goods (Purchases)
    gross_profit = total_sales_subtotal - total_purchases
    gross_margin_pct = (gross_profit / total_sales_subtotal * 100) if total_sales_subtotal else Decimal('0')

    # Net Profit = Gross Profit - Total Operating Expenses + (Debit Notes - Credit Notes)
    net_profit = gross_profit - total_expenses + (debit_notes - credit_notes)
    net_margin_pct = (net_profit / total_sales_subtotal * 100) if total_sales_subtotal else Decimal('0')

    # Outstanding / Receivables = Total Sales - Total Payments Received
    outstanding_receivables = max(Decimal('0'), total_sales - total_payments_received)

    # ── Payment Reminders & Urgent Alerts ──────────────────────────────────────
    reminders = []
    # Overdue Invoices older than 30 days
    overdue_docs = Document.objects.filter(
        type='INV', status='Approved',
        date__lt=today - timedelta(days=30)
    ).select_related('contact').order_by('date')[:5]
    for doc in overdue_docs:
        reminders.append({
            'title': f"Overdue Invoice #{doc.number or doc.id}",
            'party': doc.contact.name if doc.contact else "Customer",
            'amount': doc.grand_total,
            'date': doc.date,
            'type': 'receivable',
            'is_urgent': True,
            'link': f"/documents/{doc.id}/"
        })

    # Pending Vendor Expenses needing payment
    pending_exp_list = Expense.objects.filter(
        status='Pending'
    ).order_by('-date')[:5]
    for exp in pending_exp_list:
        reminders.append({
            'title': f"Pending Expense: {exp.expense_type}",
            'party': exp.paid_to or "Vendor",
            'amount': exp.amount,
            'date': exp.date,
            'type': 'payable',
            'is_urgent': False,
            'link': "/payments/expenses/"
        })

    # ── Monthly / Yearly trend data (last 6 intervals) ─────────────────────────
    monthly_trend = []
    for i in range(5, -1, -1):
        ref = today.replace(day=1) - timedelta(days=i * 28)
        m_start = ref.replace(day=1)
        if m_start.month == 12:
            m_end = date(m_start.year + 1, 1, 1) - timedelta(days=1)
        else:
            m_end = date(m_start.year, m_start.month + 1, 1) - timedelta(days=1)

        m_sales = Document.objects.filter(
            type__in=['INV', 'PRO'], status='Approved',
            date__gte=m_start, date__lte=m_end
        ).aggregate(t=Sum('grand_total'))['t'] or Decimal('0')

        m_purchases = Document.objects.filter(
            type='PO', status='Approved',
            date__gte=m_start, date__lte=m_end
        ).aggregate(t=Sum('grand_total'))['t'] or Decimal('0')

        m_exp = Expense.objects.filter(
            status='Approved', date__gte=m_start, date__lte=m_end
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

        m_profit = m_sales - m_purchases - m_exp

        monthly_trend.append({
            'month': m_start.strftime('%b %Y'),
            'sales': float(m_sales),
            'purchases': float(m_purchases),
            'expenses': float(m_exp),
            'profit': float(m_profit),
        })

    # ── Expense breakdown by category ─────────────────────────────────────────
    expense_by_type = list(
        expenses_qs.values('expense_type')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')[:8]
    )

    # ── Top customers by sales value ─────────────────────────────────────────
    top_customers = list(
        sales_qs.values('contact__name')
        .annotate(total=Sum('grand_total'), count=Count('id'))
        .order_by('-total')[:5]
    )

    periods = [
        ('today', 'Today'),
        ('this_week', 'This Week'),
        ('this_month', 'This Month'),
        ('last_month', 'Last Month'),
        ('this_quarter', 'This Quarter'),
        ('this_fy', 'This FY'),
        ('this_year', 'This Year'),
    ]

    context = {
        # Period
        'period': period,
        'periods': periods,
        'label': label,
        'start_date': start_date,
        'end_date': end_date,
        # Sales & Purchases
        'total_sales': total_sales,
        'total_sales_subtotal': total_sales_subtotal,
        'total_sales_tax': total_sales_tax,
        'sales_count': sales_count,
        'total_purchases': total_purchases,
        'purchases_count': purchases_count,
        'total_quotations': total_quotations,
        'quotations_count': quotations_count,
        # Payments & Payables
        'total_payments_received': total_payments_received,
        'payments_count': payments_count,
        'outstanding_receivables': outstanding_receivables,
        'total_payments_given': total_payments_given,
        'amount_needed_to_pay': amount_needed_to_pay,
        # Orders
        'total_orders': total_orders,
        'order_open': order_open,
        'order_in_progress': order_in_progress,
        'order_completed': order_completed,
        'order_other': order_other,
        # Expenses
        'total_expenses': total_expenses,
        'daily_expenses': daily_expenses,
        'fixed_expenses': fixed_expenses,
        'expenses_count': expenses_count,
        # Profit
        'gross_profit': gross_profit,
        'gross_margin_pct': gross_margin_pct,
        'net_profit': net_profit,
        'net_margin_pct': net_margin_pct,
        # Credit/Debit Notes
        'credit_notes': credit_notes,
        'debit_notes': debit_notes,
        # Reminders
        'reminders': reminders,
        'reminder_count': len(reminders),
        # Charts
        'monthly_trend': monthly_trend,
        'expense_by_type': expense_by_type,
        'top_customers': top_customers,
    }

    return render(request, 'reporting/financial_dashboard.html', context)

