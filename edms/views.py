from core.decorators import require_permission
"""
EDMS Views
==========
All Class-Based Views for the Enterprise Document Management System.
Business logic lives in services/; views only handle HTTP concerns.
"""

import logging
import os

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import (
    FileResponse, Http404, HttpResponse, JsonResponse, HttpResponseForbidden,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.utils.timezone import now
from django.views.generic import (
    CreateView, DeleteView, DetailView,
    ListView, TemplateView, UpdateView, View,
)
from edms.forms import (
    CategoryForm, CompanyProfileForm, DepartmentForm,
    DocumentFileForm, DocumentMetadataForm, SavedSearchForm,
    SearchForm, VendorForm, VersionUploadForm,
)

from edms.mixins import (
    EDMSContextMixin, EDMSDocumentPermissionMixin,
    EDMSLoginRequiredMixin, EDMSPermissionMixin,
)
from edms.models import (
    Department, EDMSAuditLog, EDMSCompanyProfile,
    EDMSDocument, EDMSDocumentCategory, EDMSDocumentDownload,
    EDMSDocumentVersion, EDMSNotification, EDMSSavedSearch,
    EDMSVendor,
)
from edms.services.audit_service import AuditService
from edms.services.document_service import (
    DocumentService, ReportService, SearchService, VersionService,
)
from edms.services.notification_service import NotificationService
from edms.services.permission_service import PermissionService

logger  = logging.getLogger('edms.views')
User    = get_user_model()


# ─── Dashboard ────────────────────────────────────────────────────────────────

class DashboardView(EDMSLoginRequiredMixin, EDMSContextMixin, TemplateView):
    template_name = 'edms/dashboard.html'
    page_title    = 'EDMS Dashboard'

    def get_context_data(self, **kwargs):
        ctx   = super().get_context_data(**kwargs)
        stats = DocumentService.get_dashboard_stats()
        ctx.update(stats)
        return ctx


# ─── Document List ────────────────────────────────────────────────────────────

class DocumentListView(EDMSLoginRequiredMixin, EDMSContextMixin, ListView):
    template_name  = 'edms/document_list.html'
    context_object_name = 'documents'
    paginate_by    = 20
    page_title     = 'All Documents'

    def get_queryset(self):
        form = SearchForm(self.request.GET)
        filters = {}
        if form.is_valid():
            filters = form.cleaned_data
        qs = SearchService.search(
            user=self.request.user,
            filters=filters,
        ).select_related('category', 'department', 'owner', 'vendor')
        return qs

    def get_context_data(self, **kwargs):
        ctx  = super().get_context_data(**kwargs)
        ctx['search_form'] = SearchForm(self.request.GET)
        ctx['categories']  = EDMSDocumentCategory.objects.filter(is_active=True)
        ctx['departments'] = Department.objects.filter(is_active=True)
        ctx['total_count'] = self.get_queryset().count()
        # Saved searches for this user
        ctx['saved_searches'] = EDMSSavedSearch.objects.filter(user=self.request.user)
        return ctx


# ─── Document Detail ──────────────────────────────────────────────────────────

class DocumentDetailView(EDMSLoginRequiredMixin, EDMSContextMixin, DetailView):
    template_name       = 'edms/document_detail.html'
    model               = EDMSDocument
    pk_url_kwarg        = 'doc_id'
    context_object_name = 'document'
    page_title          = 'Document Details'

    def get_object(self, queryset=None):
        doc = get_object_or_404(EDMSDocument, id=self.kwargs['doc_id'])
        allowed, reason = PermissionService.has_document_access(
            self.request.user, doc, 'view'
        )
        if not allowed:
            AuditService.log(
                action=EDMSAuditLog.ACTION_FAILED_ACCESS,
                request=self.request,
                document=doc,
                description=f"View denied: {reason}",
                success=False,
                failure_reason=reason,
            )
            messages.error(self.request, f"Access denied: {reason}")
            raise Http404

        AuditService.log(
            action=EDMSAuditLog.ACTION_PREVIEW,
            request=self.request,
            document=doc,
            description=f"Viewed document '{doc.title}'",
        )
        return doc

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        doc = self.object
        ctx['versions']      = VersionService.get_versions(doc)
        ctx['audit_logs']    = doc.audit_logs.order_by('-timestamp')[:20]
        ctx['can_download']  = PermissionService.has_document_access(self.request.user, doc, 'download')[0]
        ctx['can_edit']      = PermissionService.has_document_access(self.request.user, doc, 'edit_metadata')[0]
        ctx['can_delete']    = PermissionService.has_document_access(self.request.user, doc, 'delete')[0]
        ctx['can_approve']   = PermissionService.has_document_access(self.request.user, doc, 'approve')[0]
        ctx['can_share']     = PermissionService.has_document_access(self.request.user, doc, 'share')[0]
        ctx['preview_url']   = reverse_lazy('edms:document_preview', kwargs={'doc_id': doc.id})
        return ctx


# ─── Document Upload (2-step) ─────────────────────────────────────────────────

class DocumentUploadView(EDMSPermissionMixin, EDMSContextMixin, TemplateView):
    """
    Two-step upload:
      GET  → show file selection form
      POST (step=file)     → validate file, store in session, show metadata form
      POST (step=metadata) → create document + version
    """
    template_name = 'edms/document_upload.html'
    edms_permission = 'upload'
    page_title = 'Upload Document'

    def get(self, request, *args, **kwargs):
        ctx = self.get_context_data(
            file_form=DocumentFileForm(),
            meta_form=DocumentMetadataForm(),
        )
        return render(request, self.template_name, ctx)

    def post(self, request, *args, **kwargs):
        file_form = DocumentFileForm(request.POST, request.FILES)
        meta_form = DocumentMetadataForm(request.POST)

        if file_form.is_valid() and meta_form.is_valid():
            try:
                uploaded = file_form.cleaned_data['file']

                auto_crop_str = request.POST.get('auto_crop')
                crop_points_str = request.POST.get('crop_points')
                
                if uploaded.content_type and uploaded.content_type.startswith('image/'):
                    if crop_points_str:
                        import json
                        try:
                            crop_points = json.loads(crop_points_str)
                            if isinstance(crop_points, list) and len(crop_points) == 4:
                                from mobile_upload.utils import manual_crop_document
                                from django.core.files.uploadedfile import InMemoryUploadedFile
                                from io import BytesIO
                                import os
                                
                                cropped_bytes = manual_crop_document(uploaded.read(), crop_points)
                                size = len(cropped_bytes)
                                buffer = BytesIO(cropped_bytes)
                                buffer.seek(0)
                                uploaded = InMemoryUploadedFile(
                                    buffer, 'file', 
                                    os.path.splitext(uploaded.name)[0] + ".jpg", 
                                    'image/jpeg', size, None
                                )
                        except Exception as e:
                            uploaded.seek(0)
                    elif auto_crop_str == 'true':
                        try:
                            from mobile_upload.utils import auto_crop_document
                            from django.core.files.uploadedfile import InMemoryUploadedFile
                            from io import BytesIO
                            import os
                            
                            cropped_bytes = auto_crop_document(uploaded.read())
                            size = len(cropped_bytes)
                            buffer = BytesIO(cropped_bytes)
                            buffer.seek(0)
                            uploaded = InMemoryUploadedFile(
                                buffer, 'file', 
                                os.path.splitext(uploaded.name)[0] + ".jpg", 
                                'image/jpeg', size, None
                            )
                        except Exception as e:
                            uploaded.seek(0)
                validated = meta_form.cleaned_data.copy()
                # Remove the tags field — handled separately in create_document
                tags = validated.pop('tags', [])
                new_tags_raw = validated.pop('new_tags', '')
                validated['approval_status'] = validated.get('approval_status', 'pending')

                document, version = DocumentService.create_document(
                    validated_data=validated,
                    uploaded_file=uploaded,
                    user=request.user,
                    request=request,
                )

                # Handle tags
                if tags:
                    document.tags.set(tags)
                if new_tags_raw:
                    from django.utils.text import slugify as _slug
                    for t in new_tags_raw.split(','):
                        t = t.strip()
                        if t:
                            from edms.models import EDMSDocumentTag
                            tag, _ = EDMSDocumentTag.objects.get_or_create(
                                name=t, defaults={'slug': _slug(t)[:90]}
                            )
                            document.tags.add(tag)

                messages.success(request, f"Document '{document.title}' uploaded successfully!")
                return redirect('edms:document_detail', doc_id=document.id)

            except Exception as exc:
                logger.exception("[EDMS UPLOAD] Upload failed: %s", exc)
                messages.error(request, f"Upload failed: {exc}")
        else:
            messages.error(request, 'Please fix the errors below.')

        ctx = self.get_context_data(
            file_form=file_form,
            meta_form=meta_form,
        )
        return render(request, self.template_name, ctx)


# ─── Document Metadata Edit ───────────────────────────────────────────────────

class DocumentEditView(EDMSLoginRequiredMixin, EDMSContextMixin, UpdateView):
    template_name       = 'edms/document_metadata_form.html'
    model               = EDMSDocument
    form_class          = DocumentMetadataForm
    pk_url_kwarg        = 'doc_id'
    context_object_name = 'document'
    page_title          = 'Edit Document'

    def get_object(self, queryset=None):
        doc = get_object_or_404(EDMSDocument, id=self.kwargs['doc_id'])
        allowed, reason = PermissionService.has_document_access(
            self.request.user, doc, 'edit_metadata'
        )
        if not allowed:
            messages.error(self.request, f"Access denied: {reason}")
            raise Http404
        return doc

    def form_valid(self, form):
        document = DocumentService.update_metadata(
            document=self.object,
            validated_data=form.cleaned_data,
            user=self.request.user,
            request=self.request,
        )
        messages.success(self.request, f"Document '{document.title}' updated.")
        return redirect('edms:document_detail', doc_id=document.id)


# ─── Secure Download ──────────────────────────────────────────────────────────

class DocumentDownloadView(EDMSLoginRequiredMixin, View):
    """
    Permission-checked, audit-logged secure file download.
    Files are served via Django — NEVER via direct URL.
    """

    def get(self, request, doc_id, version_number=None):
        doc = get_object_or_404(EDMSDocument, id=doc_id, is_deleted=False)

        # Permission check
        allowed, reason = PermissionService.has_document_access(request.user, doc, 'download')
        if not allowed:
            AuditService.log(
                action=EDMSAuditLog.ACTION_FAILED_ACCESS,
                request=request,
                document=doc,
                description=f"Download denied: {reason}",
                success=False,
                failure_reason=reason,
            )
            messages.error(request, f"Download denied: {reason}")
            return redirect('edms:document_detail', doc_id=doc.id)

        # Redirect commercial docs to their dedicated PDF generator endpoint
        if doc.source_type == EDMSDocument.SOURCE_COMMERCIAL and doc.commercial_doc_id:
            # Audit log the download before redirecting
            AuditService.log(
                action=EDMSAuditLog.ACTION_DOWNLOAD,
                request=request,
                document=doc,
                description=f"Downloaded commercial document PDF for '{doc.title}'",
            )
            return redirect(f'/documents/{doc.commercial_doc_id}/pdf/?download=1')

        # Get version
        if version_number:
            version = get_object_or_404(EDMSDocumentVersion, document=doc, version_number=version_number)
        else:
            version = doc.latest_version
            if not version:
                messages.error(request, 'No file found for this document.')
                return redirect('edms:document_detail', doc_id=doc.id)

        # Record download
        ip_fwd = request.META.get('HTTP_X_FORWARDED_FOR', '')
        ip     = ip_fwd.split(',')[0].strip() if ip_fwd else request.META.get('REMOTE_ADDR', '')
        EDMSDocumentDownload.objects.create(
            document=doc,
            version=version,
            downloaded_by=request.user,
            ip_address=ip or None,
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        # Audit log
        AuditService.log(
            action=EDMSAuditLog.ACTION_DOWNLOAD,
            request=request,
            document=doc,
            description=f"Downloaded v{version.version_number} of '{doc.title}'",
        )

        # Email notification to MD
        try:
            NotificationService.notify_md(
                event_type='download',
                document=doc,
                actor_request=request,
            )
        except Exception as exc:
            logger.warning("[EDMS DOWNLOAD] Notification failed: %s", exc)

        # Serve file securely
        try:
            file_path = version.file.path
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found on disk: {file_path}")

            response = FileResponse(
                open(file_path, 'rb'),
                content_type=version.mime_type or 'application/octet-stream',
            )
            filename = version.file_name or os.path.basename(file_path)
            response['Content-Disposition'] = (
                f'attachment; filename="{filename}"'
            )
            response['Content-Length'] = version.file_size
            return response

        except FileNotFoundError:
            messages.error(request, 'File not found on server. Please contact admin.')
            return redirect('edms:document_detail', doc_id=doc.id)


# ─── In-Browser Preview ───────────────────────────────────────────────────────

class DocumentPreviewView(EDMSLoginRequiredMixin, View):
    """Serve file inline for browser preview (PDF, images, text)."""

    def get(self, request, doc_id, version_number=None):
        doc = get_object_or_404(EDMSDocument, id=doc_id, is_deleted=False)
        allowed, reason = PermissionService.has_document_access(request.user, doc, 'preview')
        if not allowed:
            return HttpResponse(f"Access denied: {reason}", status=403)

        # Redirect commercial docs to their dedicated HTML preview endpoint
        if doc.source_type == EDMSDocument.SOURCE_COMMERCIAL and doc.commercial_doc_id:
            AuditService.log(
                action=EDMSAuditLog.ACTION_PREVIEW,
                request=request,
                document=doc,
                description=f"Previewed commercial document HTML for '{doc.title}'",
            )
            # Use the raw HTML preview view so it renders nicely in the iframe
            return redirect(f'/documents/{doc.commercial_doc_id}/html/')

        if version_number:
            version = get_object_or_404(EDMSDocumentVersion, document=doc, version_number=version_number)
        else:
            version = doc.latest_version
            if not version:
                return HttpResponse("No file available.", status=404)

        AuditService.log(
            action=EDMSAuditLog.ACTION_PREVIEW,
            request=request,
            document=doc,
            description=f"Previewed v{version.version_number} of '{doc.title}'",
        )

        try:
            file_path = version.file.path
            response  = FileResponse(
                open(file_path, 'rb'),
                content_type=version.mime_type or 'application/octet-stream',
            )
            response['Content-Disposition'] = f'inline; filename="{version.file_name}"'
            return response
        except FileNotFoundError:
            return HttpResponse("File not found on server.", status=404)


# ─── Document Delete ──────────────────────────────────────────────────────────

class DocumentDeleteView(EDMSLoginRequiredMixin, EDMSContextMixin, View):
    template_name = 'edms/document_confirm_delete.html'
    page_title    = 'Delete Document'

    def get(self, request, doc_id):
        doc = get_object_or_404(EDMSDocument, id=doc_id)
        allowed, reason = PermissionService.has_document_access(request.user, doc, 'delete')
        if not allowed:
            messages.error(request, f"Access denied: {reason}")
            return redirect('edms:document_detail', doc_id=doc.id)
        ctx = self.get_context_data(document=doc)
        return render(request, self.template_name, ctx)

    def post(self, request, doc_id):
        doc = get_object_or_404(EDMSDocument, id=doc_id)
        allowed, reason = PermissionService.has_document_access(request.user, doc, 'delete')
        if not allowed:
            messages.error(request, f"Access denied: {reason}")
            return redirect('edms:document_detail', doc_id=doc.id)

        reason = request.POST.get('reason', '').strip()
        permanent_delete = request.POST.get('permanent_delete') == 'on'

        if permanent_delete:
            title = doc.title
            doc.delete()
            messages.success(request, f"Document '{title}' has been permanently deleted.")
        else:
            DocumentService.soft_delete(document=doc, user=request.user, reason=reason, request=request)
            messages.success(request, f"Document '{doc.title}' has been deleted (moved to trash).")
            
        return redirect('edms:document_list')


# ─── Document Restore ─────────────────────────────────────────────────────────

class DocumentRestoreView(EDMSPermissionMixin, View):
    edms_permission = 'restore'

    def post(self, request, doc_id):
        doc = get_object_or_404(EDMSDocument, id=doc_id, is_deleted=True)
        DocumentService.restore(document=doc, user=request.user, request=request)
        messages.success(request, f"Document '{doc.title}' has been restored.")
        return redirect('edms:document_detail', doc_id=doc.id)


# ─── Document Approve ─────────────────────────────────────────────────────────

class DocumentApproveView(EDMSPermissionMixin, View):
    edms_permission = 'approve'

    def post(self, request, doc_id):
        doc = get_object_or_404(EDMSDocument, id=doc_id)
        DocumentService.approve(document=doc, user=request.user, request=request)
        messages.success(request, f"Document '{doc.title}' approved.")
        return redirect('edms:document_detail', doc_id=doc.id)


# ─── Version History ─────────────────────────────────────────────────────────

class VersionHistoryView(EDMSLoginRequiredMixin, EDMSContextMixin, TemplateView):
    template_name = 'edms/version_history.html'
    page_title    = 'Version History'

    def get(self, request, doc_id):
        doc = get_object_or_404(EDMSDocument, id=doc_id)
        allowed, reason = PermissionService.has_document_access(request.user, doc, 'view')
        if not allowed:
            messages.error(request, f"Access denied: {reason}")
            return redirect('edms:dashboard')
        versions = VersionService.get_versions(doc)
        ctx = self.get_context_data(document=doc, versions=versions)
        return render(request, self.template_name, ctx)


# ─── New Version Upload ───────────────────────────────────────────────────────

class NewVersionUploadView(EDMSLoginRequiredMixin, View):
    """Upload a new version of an existing document."""

    def post(self, request, doc_id):
        doc = get_object_or_404(EDMSDocument, id=doc_id)
        allowed, reason = PermissionService.has_document_access(
            request.user, doc, 'edit_metadata'
        )
        if not allowed:
            messages.error(request, f"Access denied: {reason}")
            return redirect('edms:document_detail', doc_id=doc.id)

        form = VersionUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                document, version = DocumentService.upload_new_version(
                    document=doc,
                    uploaded_file=form.cleaned_data['file'],
                    user=request.user,
                    change_note=form.cleaned_data.get('change_note', ''),
                    request=request,
                )
                messages.success(
                    request,
                    f"New version v{version.version_number} uploaded for '{doc.title}'."
                )
            except Exception as exc:
                messages.error(request, f"Upload failed: {exc}")
        else:
            for error in form.errors.values():
                messages.error(request, str(error))

        return redirect('edms:version_history', doc_id=doc.id)


# ─── Search ──────────────────────────────────────────────────────────────────

class SearchView(EDMSLoginRequiredMixin, EDMSContextMixin, ListView):
    template_name       = 'edms/search.html'
    context_object_name = 'documents'
    paginate_by         = 20
    page_title          = 'Search Documents'

    def get_queryset(self):
        form = SearchForm(self.request.GET)
        if form.is_valid():
            AuditService.log(
                action=EDMSAuditLog.ACTION_SEARCH,
                request=self.request,
                description=f"Search: {self.request.GET.get('q', '')}",
            )
            return SearchService.search(
                user=self.request.user,
                filters=form.cleaned_data,
            ).select_related('category', 'department', 'owner', 'vendor')
        return EDMSDocument.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['search_form']    = SearchForm(self.request.GET)
        ctx['categories']     = EDMSDocumentCategory.objects.filter(is_active=True)
        ctx['departments']    = Department.objects.filter(is_active=True)
        ctx['saved_searches'] = EDMSSavedSearch.objects.filter(user=self.request.user)
        return ctx


# ─── Save Search ──────────────────────────────────────────────────────────────

class SaveSearchView(EDMSLoginRequiredMixin, View):
    def post(self, request):
        form = SavedSearchForm(request.POST)
        if form.is_valid():
            EDMSSavedSearch.objects.update_or_create(
                user=request.user,
                name=form.cleaned_data['name'],
                defaults={
                    'filters': dict(request.POST),
                    'description': form.cleaned_data.get('description', ''),
                },
            )
            messages.success(request, f"Search '{form.cleaned_data['name']}' saved.")
        return redirect(request.META.get('HTTP_REFERER', 'edms:search'))


# ─── Audit Log ────────────────────────────────────────────────────────────────

class AuditLogView(EDMSPermissionMixin, EDMSContextMixin, ListView):
    template_name       = 'edms/audit_log.html'
    model               = EDMSAuditLog
    context_object_name = 'logs'
    paginate_by         = 50
    edms_permission     = 'view_audit_log'
    page_title          = 'Audit Logs'

    def get_queryset(self):
        qs = EDMSAuditLog.objects.select_related('user', 'document').order_by('-timestamp')
        # Filter controls
        action = self.request.GET.get('action')
        user   = self.request.GET.get('user')
        date   = self.request.GET.get('date')
        if action:
            qs = qs.filter(action=action)
        if user:
            qs = qs.filter(username_cached__icontains=user)
        if date:
            qs = qs.filter(timestamp__date=date)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['action_choices'] = EDMSAuditLog.ACTION_CHOICES
        ctx['filter_action']  = self.request.GET.get('action', '')
        ctx['filter_user']    = self.request.GET.get('user', '')
        ctx['filter_date']    = self.request.GET.get('date', '')
        return ctx


# ─── Reports ─────────────────────────────────────────────────────────────────

class ReportsView(EDMSPermissionMixin, EDMSContextMixin, TemplateView):
    template_name   = 'edms/reports.html'
    edms_permission = 'view_reports'
    page_title      = 'Reports'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        report_type = self.request.GET.get('type', 'upload')
        filters = {
            'date_from': self.request.GET.get('date_from'),
            'date_to':   self.request.GET.get('date_to'),
        }
        if report_type == 'upload':
            ctx['report_data']  = ReportService.upload_report(filters)
        elif report_type == 'download':
            ctx['report_data']  = ReportService.download_report(filters)
        elif report_type == 'expiry':
            ctx['report_data']  = ReportService.expiry_report()
        elif report_type == 'vendor':
            ctx['report_data']  = ReportService.vendor_report()
        elif report_type == 'storage':
            ctx['report_data']  = ReportService.storage_report()
        else:
            ctx['report_data']  = ReportService.upload_report(filters)

        ctx['report_type']  = report_type
        ctx['filters']      = filters
        return ctx


# ─── Vendor CRUD ─────────────────────────────────────────────────────────────

class VendorListView(EDMSLoginRequiredMixin, EDMSContextMixin, ListView):
    template_name       = 'edms/vendors/list.html'
    model               = EDMSVendor
    context_object_name = 'vendors'
    paginate_by         = 20
    page_title          = 'Vendors'

    def get_queryset(self):
        qs = EDMSVendor.objects.all().order_by('name')
        q  = self.request.GET.get('q', '')
        if q:
            from django.db.models import Q
            qs = qs.filter(Q(name__icontains=q) | Q(gst_number__icontains=q))
        return qs


class VendorCreateView(EDMSPermissionMixin, EDMSContextMixin, CreateView):
    template_name   = 'edms/vendors/form.html'
    model           = EDMSVendor
    form_class      = VendorForm
    success_url     = reverse_lazy('edms:vendor_list')
    edms_permission = 'upload'
    page_title      = 'Add Vendor'

    def form_valid(self, form):
        messages.success(self.request, f"Vendor '{form.cleaned_data['name']}' created.")
        return super().form_valid(form)


class VendorEditView(EDMSPermissionMixin, EDMSContextMixin, UpdateView):
    template_name   = 'edms/vendors/form.html'
    model           = EDMSVendor
    form_class      = VendorForm
    pk_url_kwarg    = 'vendor_id'
    success_url     = reverse_lazy('edms:vendor_list')
    edms_permission = 'edit_metadata'
    page_title      = 'Edit Vendor'

    def form_valid(self, form):
        messages.success(self.request, 'Vendor updated.')
        return super().form_valid(form)


# ─── Category CRUD ───────────────────────────────────────────────────────────

class CategoryListView(EDMSPermissionMixin, EDMSContextMixin, ListView):
    template_name       = 'edms/categories/list.html'
    model               = EDMSDocumentCategory
    context_object_name = 'categories'
    edms_permission     = 'manage_categories'
    page_title          = 'Document Categories'


class CategoryCreateView(EDMSPermissionMixin, EDMSContextMixin, CreateView):
    template_name   = 'edms/categories/form.html'
    model           = EDMSDocumentCategory
    form_class      = CategoryForm
    success_url     = reverse_lazy('edms:category_list')
    edms_permission = 'manage_categories'
    page_title      = 'Add Category'

    def form_valid(self, form):
        messages.success(self.request, f"Category '{form.cleaned_data['name']}' created.")
        return super().form_valid(form)


class CategoryEditView(EDMSPermissionMixin, EDMSContextMixin, UpdateView):
    template_name   = 'edms/categories/form.html'
    model           = EDMSDocumentCategory
    form_class      = CategoryForm
    pk_url_kwarg    = 'cat_id'
    success_url     = reverse_lazy('edms:category_list')
    edms_permission = 'manage_categories'
    page_title      = 'Edit Category'


# ─── Company Profile ─────────────────────────────────────────────────────────

class CompanyProfileView(EDMSPermissionMixin, EDMSContextMixin, View):
    template_name   = 'edms/company/form.html'
    edms_permission = 'manage_settings'
    page_title      = 'Company Profile'

    def _get_profile(self):
        return EDMSCompanyProfile.objects.first()

    def get(self, request):
        profile = self._get_profile()
        form    = CompanyProfileForm(instance=profile)
        ctx     = self.get_context_data(form=form, profile=profile)
        return render(request, self.template_name, ctx)

    def post(self, request):
        profile = self._get_profile()
        form    = CompanyProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Company profile updated.')
            return redirect('edms:company_profile')
        ctx = self.get_context_data(form=form, profile=profile)
        return render(request, self.template_name, ctx)


# ─── Department CRUD ──────────────────────────────────────────────────────────

class DepartmentListView(EDMSPermissionMixin, EDMSContextMixin, ListView):
    template_name       = 'edms/admin/department_list.html'
    model               = Department
    context_object_name = 'departments'
    edms_permission     = 'manage_settings'
    page_title          = 'Departments'


class DepartmentCreateView(EDMSPermissionMixin, EDMSContextMixin, CreateView):
    template_name   = 'edms/admin/department_form.html'
    model           = Department
    form_class      = DepartmentForm
    success_url     = reverse_lazy('edms:department_list')
    edms_permission = 'manage_settings'
    page_title      = 'Add Department'

    def form_valid(self, form):
        messages.success(self.request, f"Department '{form.cleaned_data['name']}' created.")
        return super().form_valid(form)


# ─── Admin Settings ───────────────────────────────────────────────────────────

class AdminSettingsView(EDMSPermissionMixin, EDMSContextMixin, TemplateView):
    template_name   = 'edms/admin/settings.html'
    edms_permission = 'manage_settings'
    page_title      = 'Admin Settings'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from django.conf import settings as dj_settings
        ctx['edms_settings'] = {
            'MAX_UPLOAD_MB':       getattr(dj_settings, 'EDMS_MAX_UPLOAD_MB', 50),
            'ALLOWED_EXTENSIONS':  getattr(dj_settings, 'EDMS_ALLOWED_EXTENSIONS', []),
            'STORAGE_ROOT':        str(getattr(dj_settings, 'EDMS_STORAGE_ROOT', '')),
            'MD_EMAIL':            getattr(dj_settings, 'EDMS_MD_EMAIL', ''),
            'NOTIFY_EMAILS':       getattr(dj_settings, 'EDMS_NOTIFY_EMAILS', []),
        }
        ctx['user_count'] = User.objects.filter(is_active=True).count()
        ctx['users']      = User.objects.all().order_by('role', 'username')
        return ctx


# ─── Notifications API ────────────────────────────────────────────────────────

class NotificationListView(EDMSLoginRequiredMixin, View):
    """JSON API: return unread notifications for this user."""

    def get(self, request):
        notifications = EDMSNotification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).order_by('-created_at')[:20]
        data = [
            {
                'id':         n.id,
                'title':      n.title,
                'message':    n.message,
                'action_url': n.action_url,
                'created_at': n.created_at.isoformat(),
            }
            for n in notifications
        ]
        return JsonResponse({'notifications': data, 'count': len(data)})


class MarkNotificationReadView(EDMSLoginRequiredMixin, View):
    def post(self, request, notif_id):
        notif = get_object_or_404(EDMSNotification, id=notif_id, recipient=request.user)
        notif.mark_read()
        return JsonResponse({'status': 'ok'})

class CheckInvoiceNumberView(EDMSLoginRequiredMixin, View):
    """API endpoint to check if an invoice number already exists."""
    def get(self, request, *args, **kwargs):
        invoice_number = request.GET.get('invoice_number', '').strip()
        if invoice_number and EDMSDocument.objects.filter(invoice_number__iexact=invoice_number).exists():
            return JsonResponse({'exists': True})
        return JsonResponse({'exists': False})


# ─── Download Center ──────────────────────────────────────────────────────────

class DownloadCenterView(EDMSLoginRequiredMixin, EDMSContextMixin, ListView):
    template_name       = 'edms/download_center.html'
    context_object_name = 'downloads'
    paginate_by         = 30
    page_title          = 'Download Center'

    def get_queryset(self):
        return (
            EDMSDocumentDownload.objects
            .filter(downloaded_by=self.request.user)
            .select_related('document', 'version')
            .order_by('-created_at')
        )
