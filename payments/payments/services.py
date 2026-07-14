from django.db.models import Sum
from documents.models import Document
from .models import Payment

class CustomerLedgerService:
    @staticmethod
    def get_outstanding_balance(contact_id):
        invoices_total = Document.objects.filter(
            contact_id=contact_id, 
            type='INV', 
            status='Approved'
        ).aggregate(Sum('grand_total'))['grand_total__sum'] or 0
        
        payments_total = Payment.objects.filter(
            contact_id=contact_id
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        return invoices_total - payments_total
