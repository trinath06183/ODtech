from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, OTPToken

admin.site.register(User, UserAdmin)


@admin.register(OTPToken)
class OTPTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'otp', 'created_at', 'expires_at', 'used')
    list_filter = ('used',)
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('user', 'otp', 'created_at', 'expires_at')
    ordering = ('-created_at',)
