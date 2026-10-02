"""
core/audit_registry.py
======================
Central registration of all models to be tracked by the audit system.

To add a new model: import it and call register_audit().
track_fields lists the specific fields whose values will be captured
in old_values / new_values on every save/delete.
"""
from core.audit import register_audit


# ------------------------------------------------------------------
# Payments
# ------------------------------------------------------------------
from payments.models import Payment

register_audit(
    Payment,
    track_fields=[
        'contact_id', 'document_ref', 'amount',
        'payment_mode', 'reference_number', 'date', 'notes',
    ],
)


# ------------------------------------------------------------------
# Contacts
# ------------------------------------------------------------------
from contacts.models import Contact

register_audit(
    Contact,
    track_fields=[
        'name', 'contact_type', 'email', 'phone',
        'address', 'gstin', 'pan',
    ],
)


# ------------------------------------------------------------------
# Documents
# ------------------------------------------------------------------
from documents.models import Document

register_audit(
    Document,
    track_fields=[
        'number', 'type', 'status', 'contact_id',
        'date', 'grand_total', 'currency', 'exchange_rate',
        'notes', 'terms',
    ],
)


# ------------------------------------------------------------------
# Inventory / Products
# ------------------------------------------------------------------
from inventory.models import Product, StockTransaction

register_audit(
    Product,
    track_fields=[
        'name', 'sku', 'unit', 'category',
        'selling_price', 'cost_price', 'stock_quantity', 'is_active',
    ],
)

register_audit(
    StockTransaction,
    track_fields=[
        'product_id', 'transaction_type', 'quantity',
        'reference', 'notes',
    ],
)


# ------------------------------------------------------------------
# Users
# ------------------------------------------------------------------
from django.contrib.auth import get_user_model
User = get_user_model()

register_audit(
    User,
    track_fields=[
        'username', 'email', 'first_name', 'last_name',
        'role', 'is_active', 'is_staff',
    ],
)
