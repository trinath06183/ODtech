from django.contrib import admin
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('contact', 'amount', 'payment_mode', 'date', 'reference_number')
    search_fields = ('contact__name', 'reference_number')
    list_filter = ('payment_mode', 'date')
