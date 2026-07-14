from django.shortcuts import render
from django.db.models import Sum, Q
from core.decorators import login_required
from inventory.models import Product


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
