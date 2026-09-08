from django.http import JsonResponse
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from inventory.models import Product
from contacts.models import Contact
from documents.models import Document

@login_required
def global_search(request):
    q = request.GET.get('q', '').strip()
    category = request.GET.get('type', '')
    
    results = {}
    
    def get_products(query, limit=10):
        qs = Product.objects.all().order_by('-created_at')
        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(sku__icontains=query))
        
        prod_list = []
        for p in qs[:limit]:
            prod_list.append({
                'id': p.id,
                'name': p.name,
                'sku': p.sku,
                'stock_quantity': float(p.current_stock)
            })
        return prod_list

    def get_contacts(query, limit=10):
        qs = Contact.objects.all().order_by('-created_at')
        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(email__icontains=query) | Q(phone__icontains=query))
        return list(qs[:limit].values('id', 'name', 'contact_type', 'email'))

    def get_documents(query, limit=10):
        from edms.models import EDMSDocument
        import re

        doc_list = []

        # 1. Commercial Documents
        qs = Document.objects.select_related('contact').all().order_by('-date', '-created_at')
        if query:
            qs = qs.filter(Q(number__icontains=query) | Q(contact__name__icontains=query))
        for doc in qs[:limit]:
            doc_list.append({
                'id': doc.id,
                'document_number': doc.number,
                'type': doc.get_type_display(),
                'contact_name': doc.contact.name if doc.contact else 'N/A',
                'grand_total': str(doc.grand_total),
                'url': f"/documents/{doc.id}/preview/"
            })

        # 2. EDMS Documents
        edms_qs = EDMSDocument.objects.filter(is_deleted=False).order_by('-created_at')
        if query:
            clean_id = re.sub(r'^(edms|doc)[-_\s]*0*', '', query, flags=re.IGNORECASE).strip()
            edms_filter = (
                Q(document_id__icontains=query) |
                Q(title__icontains=query) |
                Q(reference_number__icontains=query) |
                Q(invoice_number__icontains=query) |
                Q(po_number__icontains=query) |
                Q(party_name__icontains=query)
            )
            if clean_id.isdigit():
                doc_num = int(clean_id)
                edms_filter |= Q(doc_seq=doc_num) | Q(document_id__iexact=f"EDMS{doc_num:08d}")
            edms_qs = edms_qs.filter(edms_filter)

        for ed in edms_qs[:limit]:
            doc_list.append({
                'id': str(ed.id),
                'document_number': f"{ed.document_id} — {ed.title}" if ed.document_id else ed.title,
                'type': 'EDMS',
                'contact_name': ed.party_name or (ed.contact_vendor.name if ed.contact_vendor else 'EDMS File'),
                'grand_total': str(ed.amount) if ed.amount else '',
                'url': f"/edms/document/{ed.id}/"
            })

        return doc_list[:limit]

    if category == 'products':
        results['products'] = get_products(q, limit=1000)
    elif category == 'contacts':
        results['contacts'] = get_contacts(q, limit=1000)
    elif category == 'documents':
        results['documents'] = get_documents(q, limit=1000)
    else:
        results['products'] = get_products(q, limit=10)
        results['contacts'] = get_contacts(q, limit=10)
        results['documents'] = get_documents(q, limit=10)
        
    return JsonResponse(results)
