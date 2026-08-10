import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from core.models import DocumentLink

@login_required
@require_POST
def create_document_link(request):
    try:
        data = json.loads(request.body)
        source_model = data.get('source_model') # e.g. 'documents.document' or 'edms.edmsdocument'
        source_id = data.get('source_id')
        target_model = data.get('target_model')
        target_id = data.get('target_id')
        link_type = data.get('link_type', 'related')

        if not all([source_model, source_id, target_model, target_id]):
            return JsonResponse({'status': 'error', 'message': 'Missing required fields'}, status=400)

        source_app, source_model_name = source_model.split('.')
        target_app, target_model_name = target_model.split('.')

        source_ct = ContentType.objects.get(app_label=source_app, model=source_model_name)
        target_ct = ContentType.objects.get(app_label=target_app, model=target_model_name)

        link, created = DocumentLink.objects.get_or_create(
            source_type=source_ct,
            source_id=source_id,
            target_type=target_ct,
            target_id=target_id,
            link_type=link_type,
            defaults={'created_by': request.user}
        )

        return JsonResponse({
            'status': 'success', 
            'message': 'Link created successfully',
            'link_id': link.id
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@login_required
@require_POST
def delete_document_link(request, link_id):
    try:
        link = DocumentLink.objects.get(id=link_id)
        # Allow deletion if admin or creator
        if getattr(request.user, 'role', '') == 'Admin' or link.created_by == request.user:
            link.delete()
            return JsonResponse({'status': 'success', 'message': 'Link removed successfully'})
        else:
            return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)
    except DocumentLink.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Link not found'}, status=404)

from django.db.models import Q
from django.views.decorators.http import require_GET
from documents.models import Document
from edms.models import EDMSDocument

@login_required
@require_GET
def search_linkable_documents(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})
        
    results = []
    
    # Search Commercial Documents
    docs = Document.objects.select_related('contact').filter(
        Q(number__icontains=query) | 
        Q(contact__name__icontains=query) |
        Q(po_reference_number__icontains=query)
    ).order_by('-date')[:15]
    
    for doc in docs:
        results.append({
            'id': doc.id,
            'title': f"{doc.get_type_display()} - {doc.number}",
            'subtitle': doc.contact.name if doc.contact else '',
            'type': 'Commercial Document',
            'icon': '📄'
        })
        
    # Search EDMS Documents
    edms_docs = EDMSDocument.objects.filter(
        Q(title__icontains=query) | 
        Q(invoice_number__icontains=query) |
        Q(po_number__icontains=query)
    ).order_by('-created_at')[:15]
    
    for doc in edms_docs:
        results.append({
            'id': doc.id,
            'title': doc.title,
            'subtitle': f"EDMS Upload - {doc.get_document_type_display()}",
            'type': 'EDMS Document',
            'icon': '📁'
        })
        
    return JsonResponse({'results': results})
