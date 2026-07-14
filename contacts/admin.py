from django.contrib import admin
from .models import Contact, Address, ContactPerson

class AddressInline(admin.TabularInline):
    model = Address
    extra = 1

class ContactPersonInline(admin.TabularInline):
    model = ContactPerson
    extra = 1

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_type', 'email', 'phone')
    search_fields = ('name', 'email', 'phone', 'gstin')
    list_filter = ('contact_type',)
    inlines = [ContactPersonInline]
