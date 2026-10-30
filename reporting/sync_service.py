import logging
import calendar
from decimal import Decimal
from datetime import date
from django.db import transaction

logger = logging.getLogger('reporting.sync')


def sync_single_document_to_plan(doc):
    """
    Sync a single Document and its DocumentItems into ExecutionPlanItem:
    - Invoices ('INV') -> plan_type='sales' (Sales Plan)
    - Quotations ('QTN', 'PRO') -> plan_type='booking' (Order Booking Plan)
    - Cancelled documents -> removes corresponding plan items
    - Future and past entries stay in sync automatically.
    """
    try:
        from reporting.models import ExecutionPlanItem
    except Exception as e:
        logger.warning(f"Could not import ExecutionPlanItem: {e}")
        return

    # If document is cancelled, remove any plan items
    if doc.status == 'Cancelled':
        ExecutionPlanItem.objects.filter(document=doc).delete()
        return

    # Map document type
    if doc.type == 'INV':
        plan_type = 'sales'
    elif doc.type in ('QTN', 'PRO'):
        plan_type = 'booking'
    else:
        # Other doc types (e.g. PO, Delivery Challans, etc.) do not belong in Sales/Booking plan
        ExecutionPlanItem.objects.filter(document=doc).delete()
        return

    if not doc.date:
        return

    month_start = doc.date.replace(day=1)

    # Customer Name
    customer_name = ''
    if doc.contact and doc.contact.name:
        customer_name = doc.contact.name.strip()
    elif getattr(doc, 'billing_name', None):
        customer_name = doc.billing_name.strip()
    else:
        customer_name = 'Customer'

    # Order Status & Supplied logic
    balance = getattr(doc, 'balance_due', None)
    grand = getattr(doc, 'grand_total', Decimal('0.00')) or Decimal('0.00')
    is_paid = (balance is not None and balance <= 0 and grand > 0) or getattr(doc, 'payment_status', '') == 'Paid'

    if plan_type == 'sales':
        if is_paid:
            order_status = f"Supplied on {doc.date.strftime('%d.%m.%y')}"
            is_supplied = True
        elif doc.status == 'Approved':
            order_status = f"Invoiced ({doc.number})"
            is_supplied = False
        else:
            order_status = f"{doc.status} ({doc.number})"
            is_supplied = False
    else:  # booking
        if doc.status == 'Approved':
            order_status = f"Confirmed ({doc.number})"
            is_supplied = False
        elif doc.status == 'Draft':
            order_status = f"Quoted - Draft ({doc.number})"
            is_supplied = False
        else:
            order_status = f"{doc.status} ({doc.number})"
            is_supplied = False

    items = list(doc.items.select_related('product').all())
    active_item_ids = []

    with transaction.atomic():
        if items:
            for idx, item in enumerate(items):
                active_item_ids.append(item.id)
                # Formulate item description
                desc = (item.name or '').strip()
                if not desc and item.product:
                    desc = (item.product.name or '').strip()
                if doc.project_name and doc.project_name.strip():
                    p_name = doc.project_name.strip()
                    if p_name.lower() not in desc.lower():
                        desc = f"{p_name} - {desc}" if desc else p_name
                if not desc:
                    desc = (item.description or 'Product / Item').strip()

                qty = item.quantity if item.quantity is not None else Decimal('1.00')
                rate = item.unit_price if item.unit_price is not None else Decimal('0.00')
                discount = getattr(item, 'discount', Decimal('0.00')) or Decimal('0.00')
                base_val = round((qty * rate) - discount, 2)
                gst = item.tax_rate if item.tax_rate is not None else Decimal('18.00')
                inc_gst = item.total if item.total is not None else round(base_val * (1 + (gst / Decimal('100'))), 2)
                uom = (item.unit or 'Nos').strip()

                plan_item = ExecutionPlanItem.objects.filter(document_item=item).first()
                if not plan_item:
                    plan_item = ExecutionPlanItem(
                        document=doc,
                        document_item=item,
                    )

                plan_item.plan_type = plan_type
                plan_item.month = month_start
                plan_item.customer_name = customer_name
                plan_item.item_description = desc
                plan_item.quantity = qty
                plan_item.uom = uom
                plan_item.probable_order_value = rate
                plan_item.total_order_value = base_val
                plan_item.gst_rate = gst
                plan_item.including_gst_amount = inc_gst
                plan_item.order_status = order_status
                plan_item.is_supplied = is_supplied
                plan_item.sort_order = idx + 1
                plan_item.save()

            # Clean up any plan items linked to this doc whose document_item was removed
            ExecutionPlanItem.objects.filter(document=doc).exclude(document_item_id__in=active_item_ids).delete()
        else:
            # Fallback if document has no line items yet
            plan_item = ExecutionPlanItem.objects.filter(document=doc, document_item__isnull=True).first()
            if not plan_item:
                plan_item = ExecutionPlanItem(document=doc)

            plan_item.plan_type = plan_type
            plan_item.month = month_start
            plan_item.customer_name = customer_name
            plan_item.item_description = doc.project_name or f"{doc.get_type_display()} {doc.number}"
            plan_item.quantity = Decimal('1.00')
            plan_item.uom = 'Set'
            plan_item.probable_order_value = doc.subtotal or Decimal('0.00')
            plan_item.total_order_value = doc.subtotal or Decimal('0.00')
            plan_item.gst_rate = Decimal('18.00')
            plan_item.including_gst_amount = doc.grand_total or Decimal('0.00')
            plan_item.order_status = order_status
            plan_item.is_supplied = is_supplied
            plan_item.sort_order = 1
            plan_item.save()


def sync_all_documents_to_plan(target_month=None):
    """
    Sync all active Invoices and Quotations into ExecutionPlanItem.
    If target_month is provided (YYYY-MM-01 date), only syncs docs for that month.
    Otherwise syncs across all months.
    """
    try:
        from documents.models import Document
    except Exception as e:
        logger.warning(f"Could not import Document: {e}")
        return 0

    qs = Document.objects.filter(
        type__in=['INV', 'QTN', 'PRO']
    ).exclude(status='Cancelled')

    if target_month:
        start_date = target_month.replace(day=1)
        last_day = calendar.monthrange(start_date.year, start_date.month)[1]
        end_date = target_month.replace(day=last_day)
        qs = qs.filter(date__gte=start_date, date__lte=end_date)

    count = 0
    for doc in qs.prefetch_related('items__product', 'contact'):
        try:
            sync_single_document_to_plan(doc)
            count += 1
        except Exception as e:
            logger.error(f"Error syncing document {getattr(doc, 'number', '?')}: {e}", exc_info=True)
    return count

