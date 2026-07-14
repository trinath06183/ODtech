from django.db import models
from django.conf import settings

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SystemActivityLog(models.Model):
    """Tracks global system actions (POST/PUT/DELETE) for security auditing."""
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    method     = models.CharField(max_length=10)
    path       = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    payload    = models.JSONField(null=True, blank=True)
    timestamp  = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user} - {self.method} {self.path}"
