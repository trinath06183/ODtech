import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp_project.settings.sqlite')
django.setup()

from documents.models import Document
from tracker.models import Order, Product as TrackerProduct

pi = Document.objects.filter(type='PRO').first()
print(f"Testing with PI: {pi.id}, {pi.number}")
print(f"PI is_in_tracker before: {pi.is_in_tracker}")
print(f"PI items count: {pi.items.count()}")
for item in pi.items.all():
    print(f"Item: name='{item.name}', product={item.product}, qty={item.quantity}, unit_price={item.unit_price}, tax_rate={item.tax_rate}")
