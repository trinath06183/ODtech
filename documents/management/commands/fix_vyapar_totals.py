from django.core.management.base import BaseCommand
from documents.models import Document

class Command(BaseCommand):
    help = 'Fix missing document totals for imported Vyapar data'

    def handle(self, *args, **options):
        docs = Document.objects.filter(grand_total=0)
        count = 0
        
        self.stdout.write(f"Found {docs.count()} documents with 0.00 total. Fixing...")
        
        for doc in docs:
            items = doc.items.all()
            if not items:
                continue
                
            sub = sum((i.quantity * i.unit_price) - i.discount for i in items)
            tax = sum(i.tax_amount for i in items)
            grand = sub + tax
            
            doc.subtotal = sub
            doc.tax_total = tax
            doc.grand_total = grand
            doc.save(update_fields=['subtotal', 'tax_total', 'grand_total'])
            count += 1
            
        self.stdout.write(self.style.SUCCESS(f"Successfully fixed totals for {count} documents!"))
