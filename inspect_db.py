import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp_project.settings.sqlite')
django.setup()

from documents.models import Document
from tracker.models import Order
from core.models import DocumentLink

print("=== ALL PROFORMA INVOICES ===")
pis = Document.objects.filter(type__in=['PRO', 'PI'])
print(f"Total PIs: {pis.count()}")
for p in pis[:10]:
    print(f"ID: {p.id}, Number: '{p.number}', Type: '{p.type}', Status: '{p.status}', PO_Ref: '{p.po_reference_number}', Project: '{p.project_name}', Contact: '{p.contact.name if p.contact else None}'")

print("\n=== RECENT ORDERS ===")
orders = Order.objects.all().order_by('-order_date')[:10]
print(f"Total Orders: {Order.objects.count()}")
for o in orders:
    print(f"ID: {o.id}, Order#: '{o.order_number}', Customer: '{o.customer_name}', Remark: '{o.remark}'")

print("\n=== ALL APPROVED DOCUMENTS ===")
appr = Document.objects.filter(status__iexact='approved')
print(f"Total approved docs: {appr.count()}")
for a in appr[:10]:
    print(f"ID: {a.id}, Number: '{a.number}', Type: '{a.type}', Status: '{a.status}', PO_Ref: '{a.po_reference_number}'")

print("\n=== DOCUMENT LINKS ===")
links = DocumentLink.objects.all()[:10]
print(f"Total links: {DocumentLink.objects.count()}")
for l in links:
    print(f"Link: {l.source_type} ({l.source_id}) -> {l.target_type} ({l.target_id}) [{l.link_type}]")
