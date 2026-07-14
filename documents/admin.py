from django.contrib import admin
from .models import Document, DocumentItem

class DocumentItemInline(admin.TabularInline):
    model = DocumentItem
    extra = 1

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('number', 'type', 'status', 'contact', 'date', 'grand_total')
    search_fields = ('number', 'contact__name')
    list_filter = ('type', 'status', 'date')
    inlines = [DocumentItemInline]
