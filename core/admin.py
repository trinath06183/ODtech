from django.contrib import admin
from .models import AuditLog, SystemActivityLog, DocumentLink


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action', 'content_type', 'object_repr', 'ip_address')
    list_filter = ('action', 'content_type', 'timestamp')
    search_fields = ('object_repr', 'user__username', 'ip_address')
    readonly_fields = ('timestamp', 'user', 'ip_address', 'action', 'content_type',
                       'object_id', 'object_repr', 'old_values', 'new_values')
    ordering = ('-timestamp',)

    def has_add_permission(self, request):
        return False  # Audit logs are read-only

    def has_delete_permission(self, request, obj=None):
        return False  # Cannot delete audit records


@admin.register(SystemActivityLog)
class SystemActivityLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'method', 'path', 'ip_address')
    list_filter = ('method', 'timestamp')
    search_fields = ('path', 'user__username')
    readonly_fields = ('timestamp', 'user', 'method', 'path', 'ip_address', 'payload')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DocumentLink)
class DocumentLinkAdmin(admin.ModelAdmin):
    list_display = ('source_type', 'source_id', 'target_type', 'target_id', 'link_type', 'created_by')
    list_filter = ('link_type',)
    search_fields = ('source_id', 'target_id')
