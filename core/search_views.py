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
        return list(qs[:limit].values('id', 'name', 'sku', 'stock_quantity'))

    def get_contacts(query, limit=10):
        qs = Contact.objects.all().order_by('-created_at')
        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(email__icontains=query) | Q(phone__icontains=query))
        return list(qs[:limit].values('id', 'name', 'contact_type', 'email'))

    def get_documents(query, limit=10):
        qs = Document.objects.select_related('contact').all().order_by('-date', '-created_at')
        if query:
            qs = qs.filter(Q(document_number__icontains=query) | Q(contact__name__icontains=query))
        
        doc_list = []
        for doc in qs[:limit]:
            doc_list.append({
                'id': doc.id,
                'document_number': doc.document_number,
                'type': doc.get_type_display(),
                'contact_name': doc.contact.name if doc.contact else 'N/A',
                'grand_total': str(doc.grand_total)
            })
        return doc_list

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
