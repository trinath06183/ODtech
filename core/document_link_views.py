import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from core.models import DocumentLink
from documents.models import Document
from edms.models import EDMSDocument

@login_required
@require_POST
def create_document_link(request):
    try:
        data = json.loads(request.body)
        source_model = data.get('source_model') # e.g. 'tracker.order', 'documents.document', 'edms.edmsdocument'
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

        # Check if already linked in either direction
        existing = DocumentLink.objects.filter(
            (Q(source_type=source_ct, source_id=str(source_id), target_type=target_ct, target_id=str(target_id))) |
            (Q(source_type=target_ct, source_id=str(target_id), target_type=source_ct, target_id=str(source_id)))
        ).first()

        if existing:
            return JsonResponse({
                'status': 'success', 
                'message': 'Document is already linked',
                'link_id': existing.id
            })

        link = DocumentLink.objects.create(
            source_type=source_ct,
            source_id=str(source_id),
            target_type=target_ct,
            target_id=str(target_id),
            link_type=link_type,
            created_by=request.user
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
        # Allow deletion if admin, staff, creator, or if creator is None
        is_admin = getattr(request.user, 'role', '') == 'Admin' or request.user.is_staff or request.user.is_superuser
        if is_admin or link.created_by == request.user or link.created_by is None:
            link.delete()
            return JsonResponse({'status': 'success', 'message': 'Link removed successfully'})
        else:
            return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)
    except DocumentLink.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Link not found'}, status=404)

@login_required
@require_POST
def unlink_document(request):
    """
    Unlinks a document from a source (e.g. an order), supporting both link_id or (source, target) pair.
    """
    try:
        data = json.loads(request.body)
        link_id = data.get('link_id')
        source_model = data.get('source_model')
        source_id = data.get('source_id')
        target_model = data.get('target_model')
        target_id = data.get('target_id')

        if link_id:
            try:
                link = DocumentLink.objects.get(id=link_id)
                link.delete()
                return JsonResponse({'status': 'success', 'message': 'Link removed successfully'})
            except DocumentLink.DoesNotExist:
                pass

        if source_model and source_id and target_model and target_id:
            source_app, source_model_name = source_model.split('.')
            target_app, target_model_name = target_model.split('.')
            source_ct = ContentType.objects.get(app_label=source_app, model=source_model_name)
            target_ct = ContentType.objects.get(app_label=target_app, model=target_model_name)

            DocumentLink.objects.filter(
                (Q(source_type=source_ct, source_id=str(source_id), target_type=target_ct, target_id=str(target_id))) |
                (Q(source_type=target_ct, source_id=str(target_id), target_type=source_ct, target_id=str(source_id)))
            ).delete()

            # If target was a Document and po_reference_number matched source order, clear it
            if target_model == 'documents.document':
                from tracker.models import Order
                try:
                    order = Order.objects.get(id=source_id)
                    doc = Document.objects.get(id=target_id)
                    if doc.po_reference_number and doc.po_reference_number.strip().lower() == order.order_number.strip().lower():
                        doc.po_reference_number = ''
                        doc.save(update_fields=['po_reference_number'])
                except Exception:
                    pass

            return JsonResponse({'status': 'success', 'message': 'Unlinked successfully'})

        return JsonResponse({'status': 'error', 'message': 'Missing parameters for unlinking'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@login_required
@require_GET
def search_linkable_documents(request):
    query = request.GET.get('q', '').strip()
    order_id = request.GET.get('order_id', '').strip()
    results = []

    # Exclude documents already linked to this order if order_id is provided
    excluded_doc_ids = set()
    excluded_edms_ids = set()
    if order_id:
        try:
            from tracker.models import Order
            order = Order.objects.filter(id=order_id).first()
            if order:
                order_ct = ContentType.objects.get_for_model(Order)
                doc_ct = ContentType.objects.get_for_model(Document)
                edms_ct = ContentType.objects.get_for_model(EDMSDocument)

                links = DocumentLink.objects.filter(
                    (Q(source_type=order_ct, source_id=str(order.id))) |
                    (Q(target_type=order_ct, target_id=str(order.id)))
                )
                for lk in links:
                    if lk.source_type == doc_ct:
                        excluded_doc_ids.add(int(lk.source_id))
                    elif lk.target_type == doc_ct:
                        excluded_doc_ids.add(int(lk.target_id))
                    elif lk.source_type == edms_ct:
                        excluded_edms_ids.add(str(lk.source_id))
                    elif lk.target_type == edms_ct:
                        excluded_edms_ids.add(str(lk.target_id))
        except Exception:
            pass
    
    # Search Commercial Documents
    docs_qs = Document.objects.select_related('contact')
    if excluded_doc_ids:
        docs_qs = docs_qs.exclude(id__in=excluded_doc_ids)

    if query:
        docs_qs = docs_qs.filter(
            Q(number__icontains=query) | 
            Q(contact__name__icontains=query) |
            Q(po_reference_number__icontains=query) |
            Q(project_name__icontains=query)
        )
    docs = list(docs_qs.order_by('-date', '-id')[:25])
    
    for doc in docs:
        type_display = doc.get_type_display() if hasattr(doc, 'get_type_display') else doc.type
        contact_name = doc.contact.name if doc.contact else 'No Customer'
        date_str = doc.date.strftime('%d %b %Y') if doc.date else ''
        status_str = doc.get_status_display() if hasattr(doc, 'get_status_display') else (doc.status or 'Draft')
        
        results.append({
            'id': doc.id,
            'model': 'documents.document',
            'doc_type': doc.type,
            'doc_type_display': type_display,
            'number': doc.number,
            'title': f"{type_display} - {doc.number}",
            'subtitle': f"{contact_name} • {date_str} • ₹{doc.grand_total:,.2f}",
            'customer_name': contact_name,
            'date': date_str,
            'amount': float(doc.grand_total or 0),
            'status': status_str,
            'type': f"Commercial ({type_display})",
            'icon': '📄',
            'preview_url': f"/documents/{doc.id}/preview/"
        })
        
    # Search EDMS Documents (excluding auto-synced copies of commercial documents)
    try:
        edms_qs = EDMSDocument.objects.filter(commercial_doc__isnull=True).exclude(source_type='commercial')
        if excluded_edms_ids:
            edms_qs = edms_qs.exclude(id__in=excluded_edms_ids)

        if query:
            edms_qs = edms_qs.filter(
                Q(title__icontains=query) | 
                Q(invoice_number__icontains=query) |
                Q(po_number__icontains=query) |
                Q(file_number__icontains=query)
            )
        edms_docs = list(edms_qs.order_by('-created_at')[:20])
        
        for doc in edms_docs:
            type_display = doc.get_document_type_display() if hasattr(doc, 'get_document_type_display') else (doc.document_type or 'File')
            try:
                from django.urls import reverse
                preview_url = reverse('edms:document_preview', args=[doc.id])
            except Exception:
                preview_url = f'/edms/document/{doc.id}/preview/'

            ref_num = doc.invoice_number or doc.po_number or doc.reference_number or doc.title
            date_str = doc.created_at.strftime('%d %b %Y') if doc.created_at else ''

            results.append({
                'id': str(doc.id),
                'model': 'edms.edmsdocument',
                'doc_type': 'EDMS',
                'doc_type_display': type_display,
                'number': ref_num,
                'title': doc.title,
                'subtitle': f"EDMS Record • {type_display} • {date_str}",
                'customer_name': doc.party_name or (doc.contact_vendor.name if doc.contact_vendor else ''),
                'date': date_str,
                'amount': float(doc.amount) if doc.amount else 0,
                'status': doc.get_approval_status_display() if hasattr(doc, 'get_approval_status_display') else doc.approval_status,
                'type': 'EDMS Document',
                'icon': '📁',
                'preview_url': preview_url
            })
    except Exception:
        pass
        
    return JsonResponse({'results': results})
