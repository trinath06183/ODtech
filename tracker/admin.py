from django.contrib import admin
from .models import Order, Lot, Product, SupplierCostOption, ErrorLog

class BaseAdmin(admin.ModelAdmin):
    readonly_fields = ('created_by', 'updated_by', 'created_at', 'updated_at')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for instance in instances:
            if not instance.pk:
                instance.created_by = request.user
            instance.updated_by = request.user
            instance.save()
        formset.save_m2m()

@admin.register(Order)
class OrderAdmin(BaseAdmin):
    list_display = ('order_number', 'customer_name', 'order_status', 'payment_status', 'order_date')
    search_fields = ('order_number', 'customer_name')
    list_filter = ('order_status', 'payment_status')

@admin.register(Lot)
class LotAdmin(BaseAdmin):
    list_display = ('lot_name', 'order')
    search_fields = ('lot_name', 'order__order_number')

class SupplierCostOptionInline(admin.TabularInline):
    model = SupplierCostOption
    extra = 1
    readonly_fields = ('created_by', 'updated_by', 'created_at', 'updated_at')

@admin.register(Product)
class ProductAdmin(BaseAdmin):
    list_display = ('item_name', 'order', 'lot', 'quantity', 'status')
    search_fields = ('item_name', 'order__order_number')
    list_filter = ('status', 'lot')
    inlines = [SupplierCostOptionInline]

@admin.register(SupplierCostOption)
class SupplierCostOptionAdmin(BaseAdmin):
    list_display = ('supplier_name', 'product', 'base_price', 'total_inc_gst', 'is_selected')
    search_fields = ('supplier_name', 'product__item_name')
    list_filter = ('is_selected',)


@admin.register(ErrorLog)
class ErrorLogAdmin(admin.ModelAdmin):
    list_display = (
        'reference_id',
        'status_code',
        'error_type',
        'error_message_short',
        'http_method',
        'url',
        'user',
        'timestamp',
        'is_resolved',
    )
    list_filter = ('status_code', 'error_type', 'http_method', 'is_resolved', 'environment', 'timestamp')
    search_fields = ('reference_id', 'error_type', 'error_message', 'url', 'stack_trace')
    list_editable = ('is_resolved',)
    readonly_fields = (
        'reference_id',
        'timestamp',
        'environment',
        'status_code',
        'error_type',
        'error_message',
        'stack_trace',
        'url',
        'http_method',
        'query_params',
        'post_data',
        'user',
        'ip_address',
        'user_agent',
    )
    ordering = ('-timestamp',)

    @admin.display(description="Error Message")
    def error_message_short(self, obj):
        if not obj.error_message:
            return "-"
        return (obj.error_message[:80] + '...') if len(obj.error_message) > 80 else obj.error_message
