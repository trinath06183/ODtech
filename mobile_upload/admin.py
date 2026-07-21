from django.contrib import admin
from .models import MobileUploadSession


@admin.register(MobileUploadSession)
class MobileUploadSessionAdmin(admin.ModelAdmin):
    list_display  = ('token', 'created_by', 'status', 'original_filename', 'created_at', 'expires_at')
    list_filter   = ('status',)
    readonly_fields = ('token', 'created_by', 'created_at', 'expires_at', 'uploaded_file',
                       'original_filename', 'file_size', 'file_mime')
    search_fields = ('created_by__username', 'original_filename')
    ordering      = ('-created_at',)
