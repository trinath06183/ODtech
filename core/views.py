from decimal import Decimal
from django.db.models import Sum, Count
from django.shortcuts import render
from django.utils import timezone
import datetime

from core.decorators import login_required
from inventory.models import Product, StockTransaction
from tracker.models import UserTodo, UserNote


def _get_period_boundaries():
    """Return (month_start, fy_start) as date objects using Indian FY (Apr–Mar)."""
    today = timezone.localdate()
    month_start = today.replace(day=1)
    # Indian FY starts April 1
    fy_year = today.year if today.month >= 4 else today.year - 1
    fy_start = datetime.date(fy_year, 4, 1)
    return month_start, fy_start


def _sales_kpis(month_start, fy_start):
    """Total Sales = Approved Invoices grand_total."""
    from documents.models import Document
    base_qs = Document.objects.filter(type='INV', status='Approved')
    month_val = base_qs.filter(date__gte=month_start).aggregate(t=Sum('grand_total'))['t'] or Decimal('0')
    fy_val    = base_qs.filter(date__gte=fy_start).aggregate(t=Sum('grand_total'))['t'] or Decimal('0')
    return month_val, fy_val


def _orders_received_kpis(month_start, fy_start):
    """Count of all tracker Orders created in period."""
    from tracker.models import Order
    month_count = Order.objects.filter(created_at__date__gte=month_start).count()
    fy_count    = Order.objects.filter(created_at__date__gte=fy_start).count()
    return month_count, fy_count


def _orders_completed_kpis(month_start, fy_start):
    """Count of CLOSED tracker Orders — filtered by updated_at in period."""
    from tracker.models import Order
    base_qs = Order.objects.filter(order_status='CLOSED')
    month_count = base_qs.filter(updated_at__date__gte=month_start).count()
    fy_count    = base_qs.filter(updated_at__date__gte=fy_start).count()
    return month_count, fy_count


def _doc_kpis(month_start, fy_start):
    """Commercial document count and total grand_total value."""
    from documents.models import Document
    def _agg(qs):
        r = qs.aggregate(cnt=Count('id'), val=Sum('grand_total'))
        return r['cnt'] or 0, r['val'] or Decimal('0')

    base_qs = Document.objects.all()
    month_cnt, month_val = _agg(base_qs.filter(date__gte=month_start))
    fy_cnt,    fy_val    = _agg(base_qs.filter(date__gte=fy_start))
    return (month_cnt, month_val), (fy_cnt, fy_val)


def _legacy_kpis():
    """Existing Total Sales / Purchases / Net P&L / Receivables for the lower cards."""
    from documents.models import Document
    from payments.models import Payment

    total_sales = Document.objects.filter(
        type='INV', status='Approved'
    ).aggregate(t=Sum('grand_total'))['t'] or Decimal('0')

    total_purchases = Document.objects.filter(
        type='PO', status='Approved'
    ).aggregate(t=Sum('grand_total'))['t'] or Decimal('0')

    net_pl = total_sales - total_purchases

    # Receivables: approved invoices minus payments received
    total_invoiced = Document.objects.filter(
        type='INV', status='Approved'
    ).aggregate(t=Sum('grand_total'))['t'] or Decimal('0')
    total_paid = Payment.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    receivable_total = max(total_invoiced - total_paid, Decimal('0'))

    today = timezone.localdate()
    d30 = today - datetime.timedelta(days=30)
    d60 = today - datetime.timedelta(days=60)
    d90 = today - datetime.timedelta(days=90)

    overdue_30 = Document.objects.filter(type='INV', status='Approved', date__range=(d60, d30)).aggregate(t=Sum('grand_total'))['t'] or Decimal('0')
    overdue_60 = Document.objects.filter(type='INV', status='Approved', date__range=(d90, d60)).aggregate(t=Sum('grand_total'))['t'] or Decimal('0')
    overdue_90 = Document.objects.filter(type='INV', status='Approved', date__lt=d90).aggregate(t=Sum('grand_total'))['t'] or Decimal('0')

    receivables = {
        'total':      receivable_total,
        'overdue_30': overdue_30,
        'overdue_60': overdue_60,
        'overdue_90': overdue_90,
    }
    return total_sales, total_purchases, net_pl, receivables


@login_required
def dashboard(request):
    # ─── Todos and Notes ───────────────────────────────────────────────────────
    recent_todos = UserTodo.objects.filter(user=request.user).order_by('is_completed', '-created_at')[:5]
    recent_notes = UserNote.objects.filter(user=request.user).order_by('-created_at')[:5]

    # ── Inventory value ──────────────────────────────────────────────────────
    products = Product.objects.all()
    total_inventory_value = Decimal('0.00')
    for p in products:
        stock = p.current_stock or Decimal('0')
        total_inventory_value += Decimal(str(stock)) * p.selling_price

    total_products = products.count()

    # ── Recent stock movements ───────────────────────────────────────────────
    recent_stock = (
        StockTransaction.objects
        .select_related('product')
        .order_by('-id')[:6]
    )

    # ── EDMS stats (lazy import to avoid circular import issues) ─────────────
    edms_doc_count = 0
    edms_recent_docs = []
    try:
        from edms.models import EDMSDocument
        edms_doc_count = EDMSDocument.objects.filter(is_deleted=False).count()
        edms_recent_docs = (
            EDMSDocument.objects
            .filter(is_deleted=False)
            .select_related('category', 'owner')
            .order_by('-created_at')[:5]
        )
    except Exception:
        pass

    low_stock_count = sum(1 for p in products if p.is_low_stock)

    # ── New KPI Metrics (Month + FY) ─────────────────────────────────────────
    month_start, fy_start = _get_period_boundaries()
    today = timezone.localdate()
    fy_year = today.year if today.month >= 4 else today.year - 1

    sales_month,    sales_fy    = _sales_kpis(month_start, fy_start)
    orders_recv_m,  orders_recv_fy  = _orders_received_kpis(month_start, fy_start)
    orders_done_m,  orders_done_fy  = _orders_completed_kpis(month_start, fy_start)
    (doc_cnt_m, doc_val_m), (doc_cnt_fy, doc_val_fy) = _doc_kpis(month_start, fy_start)

    # ── Legacy KPIs (for the existing cards below) ───────────────────────────
    try:
        total_sales, total_purchases, net_pl, receivables = _legacy_kpis()
    except Exception:
        total_sales = total_purchases = net_pl = Decimal('0')
        receivables = {'total': Decimal('0'), 'overdue_30': Decimal('0'), 'overdue_60': Decimal('0'), 'overdue_90': Decimal('0')}

    return render(request, 'core/dashboard.html', {
        # Inventory
        'total_inventory_value': total_inventory_value,
        'total_products':        total_products,
        'recent_stock':          recent_stock,
        'low_stock_count':       low_stock_count,
        # Personal
        'recent_todos':          recent_todos,
        'recent_notes':          recent_notes,
        # EDMS
        'edms_doc_count':        edms_doc_count,
        'edms_recent_docs':      edms_recent_docs,
        # ── New KPI Metrics ──
        'month_label':           month_start.strftime('%b %Y'),
        'fy_label':              f'FY {fy_year}–{str(fy_year + 1)[-2:]}',
        # Total Sales
        'sales_month':           sales_month,
        'sales_fy':              sales_fy,
        # Orders Received
        'orders_recv_m':         orders_recv_m,
        'orders_recv_fy':        orders_recv_fy,
        # Orders Completed
        'orders_done_m':         orders_done_m,
        'orders_done_fy':        orders_done_fy,
        # Documents
        'doc_cnt_m':             doc_cnt_m,
        'doc_val_m':             doc_val_m,
        'doc_cnt_fy':            doc_cnt_fy,
        'doc_val_fy':            doc_val_fy,
        # Legacy KPIs
        'total_sales':           total_sales,
        'total_purchases':       total_purchases,
        'net_pl':                net_pl,
        'receivables':           receivables,
    })


from django.views.generic import View, ListView
from django.contrib import messages
from django.shortcuts import redirect
from django.http import JsonResponse
from core.models import SystemActivityLog


@login_required
def dashboard_drilldown(request):
    """
    AJAX JSON endpoint powering the dashboard drill-down drawer.
    Query params:
        metric  — 'sales' | 'orders_received' | 'orders_completed' | 'documents'
        period  — 'month' | 'fy'
    Returns up to 20 records for the slide-in panel.
    """
    metric = request.GET.get('metric', '')
    period = request.GET.get('period', 'month')

    month_start, fy_start = _get_period_boundaries()
    since = month_start if period == 'month' else fy_start

    data = []

    try:
        if metric == 'sales':
            from documents.models import Document
            qs = (
                Document.objects
                .filter(type='INV', status='Approved', date__gte=since)
                .select_related('contact')
                .order_by('-date')[:20]
            )
            for d in qs:
                data.append({
                    'number':   d.number,
                    'customer': d.contact.name if d.contact else '—',
                    'date':     d.date.strftime('%d %b %Y') if d.date else '—',
                    'amount':   float(d.grand_total or 0.0),
                    'url':      f'/documents/{d.id}/preview/',
                })

        elif metric == 'orders_received':
            from tracker.models import Order
            qs = (
                Order.objects
                .filter(created_at__date__gte=since)
                .order_by('-created_at')[:20]
            )
            for o in qs:
                data.append({
                    'number':   o.order_number,
                    'customer': o.customer_name,
                    'date':     o.created_at.strftime('%d %b %Y') if o.created_at else '—',
                    'status':   o.get_order_status_display(),
                    'url':      f'/tracker/order/{o.id}/',
                })

        elif metric == 'orders_completed':
            from tracker.models import Order
            qs = (
                Order.objects
                .filter(order_status='CLOSED', updated_at__date__gte=since)
                .order_by('-updated_at')[:20]
            )
            
            data.append({
                'number': 'DEBUG',
                'customer': f"Count: {qs.count()} | since: {since} | metric: {metric}",
                'date': '—',
                'url': '#'
            })

            for o in qs:
                data.append({
                    'number':   o.order_number,
                    'customer': o.customer_name,
                    'date':     o.updated_at.strftime('%d %b %Y') if o.updated_at else '—',
                    'status':   'Closed',
                    'url':      f'/tracker/order/{o.id}/',
                })

        elif metric == 'documents':
            from documents.models import Document
            qs = (
                Document.objects
                .filter(date__gte=since)
                .select_related('contact')
                .order_by('-date')[:20]
            )
            for d in qs:
                data.append({
                    'number':   d.number,
                    'customer': d.contact.name if d.contact else '—',
                    'date':     d.date.strftime('%d %b %Y') if d.date else '—',
                    'type':     d.get_type_display(),
                    'amount':   float(d.grand_total or 0.0),
                    'url':      f'/documents/{d.id}/preview/',
                })

    except Exception as e:
        import traceback
        data.append({
            'number': 'ERROR',
            'customer': str(e),
            'date': traceback.format_exc().splitlines()[-1],
            'url': '#'
        })



# ─────────────────────────────────────────────────────────────────────────────
# Sales & Order Management Dashboard
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def sales_dashboard(request):
    """Render the Sales & Order Management Dashboard shell page."""
    return render(request, 'core/sales_dashboard.html', {
        'page_title': 'Sales Dashboard',
    })


@login_required
def sales_dashboard_api(request):
    """
    AJAX JSON endpoint for the Sales Dashboard.
    Query params:
        period  — 'today' | 'week' | 'month' | 'year'  (default: 'month')
    Returns KPIs, chart data, top customers, recent orders, and activity feed.
    """
    from documents.models import Document, DocumentItem
    from payments.models import Payment
    from tracker.models import Order
    from contacts.models import Contact
    from django.db.models import Sum, Count, Q, F
    import json

    period = request.GET.get('period', 'month')
    today = timezone.localdate()

    # ── Determine 'since' date based on period ──────────────────────────────
    if period == 'today':
        since = today
    elif period == 'week':
        since = today - datetime.timedelta(days=7)
    elif period == 'year':
        fy_year = today.year if today.month >= 4 else today.year - 1
        since = datetime.date(fy_year, 4, 1)
    else:  # month (default)
        since = today.replace(day=1)

    prev_since = since - (today - since + datetime.timedelta(days=1))

    # ── Helper to safely aggregate ──────────────────────────────────────────
    def safe_sum(qs, field='grand_total'):
        return float(qs.aggregate(t=Sum(field))['t'] or 0)

    def pct_change(current, previous):
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return round(((current - previous) / previous) * 100, 1)

    # ── Base querysets ──────────────────────────────────────────────────────
    all_docs = Document.objects.select_related('contact')
    inv_qs   = all_docs.filter(type='INV', status='Approved')
    qtn_qs   = all_docs.filter(type='QTN')
    pay_qs   = Payment.objects.all()

    # Current period
    inv_cur  = inv_qs.filter(date__gte=since)
    qtn_cur  = qtn_qs.filter(date__gte=since)
    pay_cur  = pay_qs.filter(date__gte=since)
    docs_cur = all_docs.filter(date__gte=since)
    ord_cur  = Order.objects.filter(created_at__date__gte=since)

    # Previous period (for % change)
    inv_prev = inv_qs.filter(date__gte=prev_since, date__lt=since)
    pay_prev = pay_qs.filter(date__gte=prev_since, date__lt=since)
    ord_prev = Order.objects.filter(created_at__date__gte=prev_since, created_at__date__lt=since)

    # ── KPI Values ──────────────────────────────────────────────────────────
    revenue_cur  = safe_sum(inv_cur)
    revenue_prev = safe_sum(inv_prev)
    paid_cur     = safe_sum(pay_cur, 'amount')
    paid_prev    = safe_sum(pay_prev, 'amount')

    total_invoiced_all = safe_sum(inv_qs)
    total_paid_all     = safe_sum(pay_qs, 'amount')
    outstanding        = max(total_invoiced_all - total_paid_all, 0)

    ord_count_cur  = ord_cur.count()
    ord_count_prev = ord_prev.count()
    qtn_count_cur  = qtn_cur.count()
    doc_count_cur  = docs_cur.count()

    # Status breakdown of tracker Orders
    order_statuses = (
        Order.objects
        .filter(created_at__date__gte=since)
        .values('order_status')
        .annotate(cnt=Count('id'))
    )
    status_map = {s['order_status']: s['cnt'] for s in order_statuses}

    # Payment status breakdown from tracker Orders
    payment_statuses = (
        Order.objects
        .filter(created_at__date__gte=since)
        .values('payment_status')
        .annotate(cnt=Count('id'))
    )
    pay_status_map = {s['payment_status']: s['cnt'] for s in payment_statuses}

    kpis = {
        'revenue':      {'value': revenue_cur,  'change': pct_change(revenue_cur, revenue_prev),  'label': 'Revenue'},
        'paid':         {'value': paid_cur,      'change': pct_change(paid_cur, paid_prev),        'label': 'Payments Received'},
        'outstanding':  {'value': outstanding,   'change': 0,                                       'label': 'Outstanding'},
        'quotations':   {'value': qtn_count_cur, 'change': 0,                                       'label': 'Quotations'},
        'invoices':     {'value': inv_cur.count(),'change': 0,                                      'label': 'Invoices'},
        'orders':       {'value': ord_count_cur, 'change': pct_change(ord_count_cur, ord_count_prev), 'label': 'Tracker Orders'},
        'docs':         {'value': doc_count_cur, 'change': 0,                                       'label': 'Total Docs'},
        # Order status breakdown
        'orders_open':       status_map.get('OPEN', 0),
        'orders_sourcing':   status_map.get('SOURCING', 0),
        'orders_procured':   status_map.get('PROCURED', 0),
        'orders_shipped':    status_map.get('SHIPPED', 0),
        'orders_closed':     status_map.get('CLOSED', 0),
        # Payment status breakdown
        'pay_unpaid':        pay_status_map.get('UNPAID', 0),
        'pay_partial':       pay_status_map.get('PARTIALLY_PAID', 0),
        'pay_paid':          pay_status_map.get('PAID', 0),
    }

    # ── Daily Revenue Chart (last 30 days) ──────────────────────────────────
    last30 = today - datetime.timedelta(days=29)
    daily_qs = (
        inv_qs
        .filter(date__gte=last30)
        .values('date')
        .annotate(total=Sum('grand_total'))
        .order_by('date')
    )
    daily_map = {str(r['date']): float(r['total'] or 0) for r in daily_qs}
    chart_labels = []
    chart_revenue = []
    for i in range(30):
        d = last30 + datetime.timedelta(days=i)
        chart_labels.append(d.strftime('%d %b'))
        chart_revenue.append(daily_map.get(str(d), 0))

    # ── Revenue by Doc Type ──────────────────────────────────────────────────
    doc_type_breakdown = (
        all_docs
        .filter(date__gte=since)
        .values('type')
        .annotate(total=Sum('grand_total'), count=Count('id'))
        .order_by('-total')
    )
    doc_types = [{'type': r['type'], 'total': float(r['total'] or 0), 'count': r['count']} for r in doc_type_breakdown]

    # ── Top 10 Customers by Revenue ─────────────────────────────────────────
    top_customers_qs = (
        inv_qs
        .filter(date__gte=since)
        .values('contact__id', 'contact__name')
        .annotate(total=Sum('grand_total'), count=Count('id'))
        .order_by('-total')[:10]
    )
    top_customers = []
    for r in top_customers_qs:
        cid = r['contact__id']
        # Get amount paid for this customer's invoices
        inv_nums = list(inv_qs.filter(date__gte=since, contact_id=cid).values_list('number', flat=True))
        paid_for_cust = float(Payment.objects.filter(document_ref__in=inv_nums).aggregate(t=Sum('amount'))['t'] or 0)
        invoiced = float(r['total'] or 0)
        top_customers.append({
            'name':     r['contact__name'] or '—',
            'invoiced': invoiced,
            'paid':     paid_for_cust,
            'balance':  max(invoiced - paid_for_cust, 0),
            'orders':   r['count'],
        })

    # ── Recent Tracker Orders ────────────────────────────────────────────────
    recent_orders_qs = (
        Order.objects
        .select_related('created_by')
        .order_by('-created_at')[:20]
    )
    recent_orders = []
    for o in recent_orders_qs:
        recent_orders.append({
            'id':             str(o.id),
            'order_number':   o.order_number,
            'customer':       o.customer_name,
            'status':         o.order_status,
            'status_display': o.get_order_status_display(),
            'payment_status': o.payment_status,
            'created_by':     o.created_by.get_full_name() or o.created_by.username if o.created_by else '—',
            'date':           o.order_date.strftime('%d %b %Y') if o.order_date else '—',
            'url':            f'/tracker/order/{o.id}/',
        })

    # ── Recent Activity Feed ─────────────────────────────────────────────────
    activity = []
    # Recent documents
    recent_docs_act = (
        all_docs
        .order_by('-created_at')[:10]
    )
    for d in recent_docs_act:
        activity.append({
            'time':    d.created_at.strftime('%d %b, %I:%M %p'),
            'icon':    '📄',
            'text':    f'{d.get_type_display()} {d.number} created',
            'sub':     d.contact.name if d.contact else '',
            'amount':  float(d.grand_total or 0),
            'ts':      d.created_at.timestamp(),
        })
    # Recent payments
    recent_pay_act = Payment.objects.select_related('contact').order_by('-created_at')[:10]
    for p in recent_pay_act:
        activity.append({
            'time':    p.created_at.strftime('%d %b, %I:%M %p'),
            'icon':    '💰',
            'text':    f'Payment received — {p.payment_mode}',
            'sub':     p.contact.name if p.contact else '',
            'amount':  float(p.amount or 0),
            'ts':      p.created_at.timestamp(),
        })
    # Sort combined by timestamp descending, take top 15
    activity.sort(key=lambda x: x['ts'], reverse=True)
    activity = activity[:15]
    for a in activity:
        del a['ts']  # Remove sorting key before returning

    return JsonResponse({
        'period':          period,
        'since':           str(since),
        'kpis':            kpis,
        'chart_labels':    chart_labels,
        'chart_revenue':   chart_revenue,
        'doc_types':       doc_types,
        'top_customers':   top_customers,
        'recent_orders':   recent_orders,
        'activity':        activity,
    })


@login_required
def sales_tracking_api(request):
    """
    AJAX JSON endpoint for the Sales Tracking section.
    Returns month-by-month breakdown for a given year.
    Query params:
        year  — 4-digit year, e.g. 2025 (default: current year)
        mode  — 'monthly' | 'yearly'  (default: 'monthly')
    Returns rows: month label, quotations, orders_received, orders_closed,
                  invoices_raised, invoice_value, payments_received.
    """
    from documents.models import Document
    from payments.models import Payment
    from tracker.models import Order
    from django.db.models import Sum, Count
    import calendar

    today = timezone.localdate()
    mode  = request.GET.get('mode', 'monthly')

    if mode == 'yearly':
        # Return last 5 financial years
        fy_year = today.year if today.month >= 4 else today.year - 1
        rows = []
        for y in range(fy_year, fy_year - 5, -1):
            fy_start = datetime.date(y, 4, 1)
            fy_end   = datetime.date(y + 1, 3, 31)
            label    = f'FY {y}–{str(y + 1)[-2:]}'

            qtns  = Document.objects.filter(type='QTN', date__range=(fy_start, fy_end)).count()
            ord_r = Order.objects.filter(created_at__date__range=(fy_start, fy_end)).count()
            ord_c = Order.objects.filter(order_status='CLOSED', updated_at__date__range=(fy_start, fy_end)).count()
            inv_c = Document.objects.filter(type='INV', date__range=(fy_start, fy_end)).count()
            inv_v = float(Document.objects.filter(type='INV', status='Approved', date__range=(fy_start, fy_end)).aggregate(t=Sum('grand_total'))['t'] or 0)
            pay_r = float(Payment.objects.filter(date__range=(fy_start, fy_end)).aggregate(t=Sum('amount'))['t'] or 0)

            rows.append({
                'label':     label,
                'fy_year':   y,
                'qtns':      qtns,
                'ord_recv':  ord_r,
                'ord_closed': ord_c,
                'inv_count': inv_c,
                'inv_value': inv_v,
                'pay_recv':  pay_r,
            })
        return JsonResponse({'mode': mode, 'rows': rows, 'available_years': []})

    else:
        # Monthly mode: return all 12 months for selected year
        try:
            year = int(request.GET.get('year', today.year))
        except (ValueError, TypeError):
            year = today.year

        # Build available years from data
        from django.db.models.functions import ExtractYear
        doc_years  = list(Document.objects.annotate(yr=ExtractYear('date')).values_list('yr', flat=True).distinct().order_by('-yr'))
        ord_years  = list(Order.objects.annotate(yr=ExtractYear('created_at')).values_list('yr', flat=True).distinct().order_by('-yr'))
        pay_years  = list(Payment.objects.annotate(yr=ExtractYear('date')).values_list('yr', flat=True).distinct().order_by('-yr'))
        all_years  = sorted(set(filter(None, doc_years + ord_years + pay_years)), reverse=True)
        if not all_years:
            all_years = [today.year]

        rows = []
        for month_num in range(1, 13):
            month_start = datetime.date(year, month_num, 1)
            last_day    = calendar.monthrange(year, month_num)[1]
            month_end   = datetime.date(year, month_num, last_day)
            label       = month_start.strftime('%b %Y')

            # Skip future months
            is_future = month_start > today.replace(day=1)

            if is_future:
                rows.append({
                    'label':      label,
                    'month':      month_num,
                    'qtns':       None,
                    'ord_recv':   None,
                    'ord_closed': None,
                    'inv_count':  None,
                    'inv_value':  None,
                    'pay_recv':   None,
                    'is_future':  True,
                })
                continue

            qtns  = Document.objects.filter(type='QTN', date__range=(month_start, month_end)).count()
            ord_r = Order.objects.filter(created_at__date__range=(month_start, month_end)).count()
            ord_c = Order.objects.filter(order_status='CLOSED', updated_at__date__range=(month_start, month_end)).count()
            inv_c = Document.objects.filter(type='INV', date__range=(month_start, month_end)).count()
            inv_v = float(Document.objects.filter(type='INV', status='Approved', date__range=(month_start, month_end)).aggregate(t=Sum('grand_total'))['t'] or 0)
            pay_r = float(Payment.objects.filter(date__range=(month_start, month_end)).aggregate(t=Sum('amount'))['t'] or 0)

            rows.append({
                'label':      label,
                'month':      month_num,
                'qtns':       qtns,
                'ord_recv':   ord_r,
                'ord_closed': ord_c,
                'inv_count':  inv_c,
                'inv_value':  inv_v,
                'pay_recv':   pay_r,
                'is_future':  False,
            })

        return JsonResponse({
            'mode':            mode,
            'year':            year,
            'rows':            rows,
            'available_years': all_years,
        })

class LogUnlockView(View):
    template_name = 'core/log_unlock.html'

    def get(self, request, *args, **kwargs):
        if not getattr(request.user, 'role', '') == 'Admin':
            messages.error(request, "Only Admins can view system logs.")
            return redirect('dashboard')
        return render(request, self.template_name)

    def post(self, request, *args, **kwargs):
        if not getattr(request.user, 'role', '') == 'Admin':
            return redirect('dashboard')

        password = request.POST.get('password', '')
        if request.user.check_password(password):
            # Unlock for 15 minutes
            request.session['logs_unlocked_until'] = (timezone.now() + timezone.timedelta(minutes=15)).isoformat()
            messages.success(request, "Log access granted for 15 minutes.")
            return redirect('system_logs')
        else:
            messages.error(request, "Incorrect password.")
            return render(request, self.template_name)


class SystemActivityLogView(ListView):
    template_name = 'core/activity_logs.html'
    model = SystemActivityLog
    context_object_name = 'logs'
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        if not getattr(request.user, 'role', '') == 'Admin':
            messages.error(request, "Only Admins can view system logs.")
            return redirect('dashboard')
        
        # Check if unlocked
        unlocked_until = request.session.get('logs_unlocked_until')
        if not unlocked_until:
            return redirect('log_unlock')
        
        from datetime import datetime
        try:
            unlock_time = datetime.fromisoformat(unlocked_until)
            if timezone.now() > unlock_time:
                messages.warning(request, "Your log access session has expired. Please re-enter your password.")
                return redirect('log_unlock')
        except ValueError:
            return redirect('log_unlock')

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        
        # Simple text search on path or user
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(path__icontains=q) | qs.filter(user__username__icontains=q)
        
        # Filter by method
        method = self.request.GET.get('method', '').strip()
        if method:
            qs = qs.filter(method=method.upper())
            
        return qs.select_related('user')
