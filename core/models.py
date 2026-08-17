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
    path       = models.TextField(db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    payload    = models.JSONField(null=True, blank=True)
    timestamp  = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user} - {self.method} {self.path}"


from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class DocumentLink(TimeStampedModel):
    """
    Generic mapping table linking any two objects in the system.
    Primarily used for Document Lifecycle Tracking (Quotation -> PI -> DC -> Invoice)
    and cross-linking EDMS uploads to commercial documents.
    """
    LINK_TYPES = (
        ('related', 'Related To'),
        ('converted', 'Converted To/From'),
        ('payment', 'Payment Proof'),
        ('supporting', 'Supporting Document'),
    )
    
    # The document initiating the link
    source_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='source_links')
    source_id = models.CharField(max_length=64, db_index=True)
    source_object = GenericForeignKey('source_type', 'source_id')
    
    # The document being linked to
    target_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='target_links')
    target_id = models.CharField(max_length=64, db_index=True)
    target_object = GenericForeignKey('target_type', 'target_id')
    
    link_type = models.CharField(max_length=20, choices=LINK_TYPES, default='related')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        unique_together = ('source_type', 'source_id', 'target_type', 'target_id', 'link_type')
        indexes = [
            models.Index(fields=['source_type', 'source_id']),
            models.Index(fields=['target_type', 'target_id']),
        ]

    def __str__(self):
        return f"{self.source_type.name} [{self.source_id}] -> {self.target_type.name} [{self.target_id}] ({self.link_type})"
