from django.contrib import admin
from .models import Product, StockTransaction

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'current_stock', 'unit', 'tax_rate')
    search_fields = ('name', 'sku')
    list_filter = ('category', 'brand')

@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ('product', 'transaction_type', 'quantity', 'created_at')
    list_filter = ('transaction_type',)

from .models import WarrantyRegistration, WarrantyClaim

@admin.register(WarrantyRegistration)
class WarrantyRegistrationAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'serial_number', 'company_name', 'invoice_date', 'created_at')
    search_fields = ('invoice_number', 'serial_number', 'company_name', 'email')
    list_filter = ('invoice_date', 'created_at')

@admin.register(WarrantyClaim)
class WarrantyClaimAdmin(admin.ModelAdmin):
    list_display = ('claim_number', 'registration', 'status', 'created_at')
    search_fields = ('claim_number', 'registration__invoice_number', 'registration__serial_number', 'registration__company_name')
    list_filter = ('status', 'created_at')

