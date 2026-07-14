"""
Documents → EDMS Auto-Sync Signals
====================================
Whenever a commercial document (Quotation, Invoice, Purchase Order, etc.)
is created or updated, a corresponding EDMSDocument record is automatically
created / updated in the Document Management section with all filled metadata.

No physical file is stored at creation time — the PDF can be downloaded/
previewed through the existing commercial-document PDF view.  The EDMS record
carries full metadata (title, type, reference number, amount, contact, date,
status, etc.) so it is fully searchable and auditable from Document Management.
"""

import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger('documents.signals')

# ─── Type mapping ─────────────────────────────────────────────────────────────
# maps documents.Document.type → edms.EDMSDocument.document_type
_EDMS_DOCTYPE_MAP = {
    'QTN': 'financial',   # Quotation
    'INV': 'financial',   # Invoice
    'PRO': 'financial',   # Proforma Invoice
    'CHL': 'financial',   # Delivery Challan
    'PO':  'purchase',    # Purchase Order
    'CRN': 'financial',   # Credit Note
    'DBN': 'financial',   # Debit Note
}

# maps documents.Document.type → human-readable EDMS category name
_CATEGORY_MAP = {
    'QTN': 'Quotations',
    'INV': 'Invoices',
    'PRO': 'Proforma Invoices',
    'CHL': 'Delivery Challans',
    'PO':  'Purchase Orders',
    'CRN': 'Credit Notes',
    'DBN': 'Debit Notes',
}


def _get_or_create_category(doc_type):
    """Return (or lazily create) the EDMS category for a commercial doc type."""
    from edms.models import EDMSDocumentCategory

    name = _CATEGORY_MAP.get(doc_type, 'Commercial Documents')
    category, _ = EDMSDocumentCategory.objects.get_or_create(
        name=name,
        defaults={
            'description': f'Auto-synced {name} from the Commercial Documents module.',
            'icon': '📄',
            'color': '#6366f1',
            'is_default': False,
        },
    )
    return category


def _get_system_user():
    """Return the first superuser / staff account to act as document owner."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.filter(is_superuser=True).order_by('id').first()
    if user is None:
        user = User.objects.filter(is_staff=True).order_by('id').first()
    if user is None:
        user = User.objects.order_by('id').first()
    return user


def _build_edms_metadata(doc):
    """
    Build a dict of EDMSDocument field values from a commercial Document.
    Only includes fields that are safe to set directly (excludes FKs handled
    separately and file-related fields that are not applicable here).
    """
    from edms.models import EDMSDocument

    doc_type_label = dict(doc.DOCUMENT_TYPES).get(doc.type, doc.type)

    # Build a descriptive keyword string for full-text search
    keywords_parts = [
        doc.number,
        doc.contact.name if doc.contact_id else '',
        doc.contact.gst_number if doc.contact_id and hasattr(doc.contact, 'gst_number') else '',
        doc.po_reference_number or '',
        doc.project_name or '',
        doc.place_of_supply or '',
        doc_type_label,
    ]
    # Add product names from line items
    try:
        for item in doc.items.select_related('product').all():
            keywords_parts.append(item.name or item.product.name or '')
            keywords_parts.append(item.part_number or '')
    except Exception:
        pass

    keywords = ' '.join(filter(None, keywords_parts))

    # Map commercial status → EDMS approval_status
    status_map = {
        'Draft':     EDMSDocument.APPROVAL_PENDING,
        'Approved':  EDMSDocument.APPROVAL_APPROVED,
        'Cancelled': EDMSDocument.APPROVAL_REJECTED,
    }

    return {
        'title':           f"{doc_type_label} — {doc.number}",
        'description':     (
            f"Auto-synced {doc_type_label}.\n"
            f"Customer / Vendor: {doc.contact.name if doc.contact_id else '—'}\n"
            f"Amount: ₹{doc.grand_total}\n"
            f"Status: {doc.status}\n"
            f"Date: {doc.date}"
            + (f"\nProject: {doc.project_name}" if doc.project_name else '')
            + (f"\nPO Ref: {doc.po_reference_number}" if doc.po_reference_number else '')
        ),
        'document_type':   _EDMS_DOCTYPE_MAP.get(doc.type, 'financial'),
        'keywords':        keywords,
        'reference_number': doc.number,
        'issue_date':      doc.date,
        'access_level':    EDMSDocument.ACCESS_INTERNAL,
        'approval_status': status_map.get(doc.status, EDMSDocument.APPROVAL_PENDING),
        'is_confidential': False,
        'source_type':     EDMSDocument.SOURCE_COMMERCIAL,
        # Purchase / invoice detail fields
        'po_number':       doc.po_reference_number or '',
        'invoice_number':  doc.number if doc.type in ('INV', 'PRO') else '',
        'invoice_date':    doc.date if doc.type in ('INV', 'PRO') else None,
        'amount':          doc.grand_total,
        'tax_amount':      doc.tax_total,
        'currency':        'INR',
    }


@receiver(post_save, sender='documents.Document')
def sync_commercial_doc_to_edms(sender, instance, created, **kwargs):
    """
    After every save of a commercial Document, create or update the
    corresponding EDMSDocument entry so it appears in Document Management
    with all metadata pre-filled.
    """
    try:
        from edms.models import EDMSDocument

        category  = _get_or_create_category(instance.type)
        sys_user  = _get_system_user()

        if sys_user is None:
            logger.warning("[EDMS SYNC] No user found — cannot sync document %s", instance.number)
            return

        metadata = _build_edms_metadata(instance)

        # Try to find an existing EDMS record linked to this commercial doc
        try:
            edms_doc = EDMSDocument.objects.get(commercial_doc=instance)
            # Update all metadata fields
            for field, value in metadata.items():
                setattr(edms_doc, field, value)
            edms_doc.category = category
            edms_doc.save()
            logger.info(
                "[EDMS SYNC] Updated EDMSDocument for commercial doc %s (edms_id=%s)",
                instance.number, edms_doc.id,
            )

        except EDMSDocument.DoesNotExist:
            # Create a fresh EDMS record (no file — it's a virtual/commercial doc)
            edms_doc = EDMSDocument(
                owner=sys_user,
                uploaded_by=sys_user,
                category=category,
                commercial_doc=instance,
                # No file fields — the document is rendered on-the-fly as PDF
                file_name=f"{instance.number}.pdf",
                file_extension='.pdf',
                mime_type='application/pdf',
                current_version=1,
                **metadata,
            )
            edms_doc.save()
            logger.info(
                "[EDMS SYNC] Created EDMSDocument for commercial doc %s (edms_id=%s)",
                instance.number, edms_doc.id,
            )

    except Exception as exc:
        # Never let a signal crash the main save flow
        logger.error(
            "[EDMS SYNC] Failed to sync commercial doc %s to EDMS: %s",
            getattr(instance, 'number', '?'), exc,
            exc_info=True,
        )


@receiver(post_delete, sender='documents.Document')
def remove_edms_record_on_delete(sender, instance, **kwargs):
    """
    When a commercial document is hard-deleted, soft-delete its EDMS record
    so it disappears from Document Management without destroying audit history.
    """
    try:
        from edms.models import EDMSDocument
        sys_user = _get_system_user()

        try:
            edms_doc = EDMSDocument.objects.get(commercial_doc_id=instance.id)
            edms_doc.is_deleted = True
            edms_doc.save(update_fields=['is_deleted'])
            logger.info(
                "[EDMS SYNC] Soft-deleted EDMSDocument for deleted commercial doc %s",
                instance.number,
            )
        except EDMSDocument.DoesNotExist:
            pass

    except Exception as exc:
        logger.error(
            "[EDMS SYNC] Failed to soft-delete EDMS record for doc %s: %s",
            getattr(instance, 'number', '?'), exc,
        )
