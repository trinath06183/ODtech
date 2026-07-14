from django.db.models import Sum
from .models import StockTransaction

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
