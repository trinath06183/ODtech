from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from .models import StockTransaction, BillOfMaterials, AssemblyWorkOrder


class StockService:
    @staticmethod
    def get_available_stock(product_id):
        result = StockTransaction.objects.filter(product_id=product_id).aggregate(Sum('quantity'))
        return result['quantity__sum'] or 0.00
    
    @staticmethod
    def create_transaction(product_id, transaction_type, quantity, reference_document=None, **kwargs):
        if transaction_type == 'OUT' and quantity > 0:
            quantity = -quantity
        elif transaction_type == 'IN' and quantity < 0:
            quantity = -quantity
            
        return StockTransaction.objects.create(
            product_id=product_id,
            transaction_type=transaction_type,
            quantity=quantity,
            reference_document=reference_document,
            **kwargs
        )


class AssemblyService:
    @staticmethod
    def check_materials_availability(bom, quantity_to_produce=1):
        """
        Check if all component materials for a BOM are available in stock.
        """
        all_sufficient = True
        items_report = []
        qty_multiplier = Decimal(str(quantity_to_produce))

        for item in bom.items.select_related('component_product').all():
            req_qty = item.effective_quantity * qty_multiplier
            avail_qty = Decimal(str(StockService.get_available_stock(item.component_product.id)))
            has_enough = avail_qty >= req_qty
            if not has_enough:
                all_sufficient = False
            shortage = max(Decimal('0.00'), req_qty - avail_qty)

            items_report.append({
                'item_id': item.id,
                'component_id': item.component_product.id,
                'component_name': item.component_product.name,
                'component_sku': item.component_product.sku,
                'unit': item.unit,
                'unit_req': float(item.quantity_required),
                'scrap_pct': float(item.scrap_percentage),
                'required_qty': float(req_qty),
                'available_qty': float(avail_qty),
                'shortage_qty': float(shortage),
                'has_enough': has_enough,
            })

        return {
            'is_sufficient': all_sufficient,
            'items': items_report,
        }

    @staticmethod
    @transaction.atomic
    def complete_work_order(work_order_id, serial_numbers=None, user=None):
        """
        Completes an AssemblyWorkOrder:
        1. Deducts raw component products from stock (OUT).
        2. Adds finished products to stock (IN).
        3. Updates work order status to Completed with timestamp.
        """
        work_order = AssemblyWorkOrder.objects.select_for_update().get(id=work_order_id)
        if work_order.status == 'Completed':
            raise ValueError(f"Work order {work_order.order_number} is already completed.")
        if work_order.status == 'Cancelled':
            raise ValueError("Cannot complete a cancelled work order.")

        qty_multiplier = Decimal(str(work_order.quantity_to_produce))
        bom = work_order.bom

        # 1. Deduct component items
        for item in bom.items.select_related('component_product').all():
            deduct_qty = item.effective_quantity * qty_multiplier
            StockService.create_transaction(
                product_id=item.component_product.id,
                transaction_type='OUT',
                quantity=deduct_qty,
                reference_document=work_order.order_number,
                reason="Assembly Work Order Consumption",
                remarks=f"Consumed {deduct_qty} {item.unit} for {work_order.quantity_to_produce}x {work_order.finished_product.name} (WO: {work_order.order_number})"
            )

        # 2. Add finished product
        serial_text = (serial_numbers or work_order.serial_numbers_produced or '').strip()
        StockService.create_transaction(
            product_id=work_order.finished_product.id,
            transaction_type='IN',
            quantity=work_order.quantity_to_produce,
            reference_document=work_order.order_number,
            serial_number=serial_text[:100] if serial_text else None,
            reason="Assembly Work Order Production Output",
            remarks=f"Manufactured via {work_order.order_number} using BOM {bom.bom_number}"
        )

        # 3. Mark completed
        work_order.status = 'Completed'
        work_order.completed_at = timezone.now()
        if serial_numbers:
            work_order.serial_numbers_produced = serial_numbers
        work_order.save()

        return work_order
