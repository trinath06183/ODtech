from django.db.models import Sum
from .models import Payment


class CustomerLedgerService:
    @staticmethod
    def get_outstanding_balance(contact_id):
        """Return total payments made by a contact (billing documents removed)."""
        payments_total = Payment.objects.filter(
            contact_id=contact_id
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        return payments_total
