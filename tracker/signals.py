import json
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from django.core.serializers.json import DjangoJSONEncoder
from django.forms.models import model_to_dict
from .models import Order, Lot, Product, SupplierCostOption, InternalNote, AuditLog, Task
from .middleware import get_current_user

@receiver(post_save, sender=Order)
def order_status_changed(sender, instance, created, **kwargs):
    if created:
        # Generate initial task for new orders
        Task.objects.create(
            order=instance,
            title=f"Initiate sourcing for Order {instance.order_number}",
            description="New order created. Start gathering quotes from suppliers.",
            priority='HIGH',
            due_date=timezone.now() + timedelta(hours=24)
        )
    else:
        # Check if status has changed to PROCURED
        if instance.order_status == 'PROCURED':
            task_exists = Task.objects.filter(order=instance, title__icontains="Generate PO").exists()
            if not task_exists:
                Task.objects.create(
                    order=instance,
                    title=f"Generate PO for Suppliers - Order {instance.order_number}",
                    description="Order is fully procured. Issue Purchase Orders to selected suppliers.",
                    priority='CRITICAL',
                    due_date=timezone.now() + timedelta(hours=24)
                )
        
        elif instance.order_status == 'SHIPPED':
            task_exists = Task.objects.filter(order=instance, title__icontains="Follow up with client").exists()
            if not task_exists:
                Task.objects.create(
                    order=instance,
                    title=f"Follow up with client for delivery - Order {instance.order_number}",
                    description="Ensure the shipped order is received successfully.",
                    priority='MEDIUM',
                    due_date=timezone.now() + timedelta(days=5)
                )

# --- Audit Log Signals ---

AUDIT_MODELS = [Order, Lot, Product, SupplierCostOption, InternalNote, Task]

COMMENT_AUDIT_MODELS = [InternalNote]

def serialize_dict(d):
    """Helper to convert dictionary values to JSON serializable formats, especially UUIDs."""
    serializable = {}
    for k, v in d.items():
        if v is not None:
            serializable[k] = str(v)
        else:
            serializable[k] = None
    return serializable

@receiver(pre_save)
def audit_pre_save(sender, instance, **kwargs):
    if sender in AUDIT_MODELS:
        if instance.pk:
            try:
                old_instance = sender.objects.get(pk=instance.pk)
                instance._old_data = serialize_dict(model_to_dict(old_instance))
            except sender.DoesNotExist:
                instance._old_data = {}
        else:
            instance._old_data = {}

@receiver(post_save)
def audit_post_save(sender, instance, created, **kwargs):
    if sender in AUDIT_MODELS:
        user = get_current_user()
        action = 'CREATE' if created else 'UPDATE'
        
        changes_str = "Created"
        if not created and hasattr(instance, '_old_data'):
            new_data = serialize_dict(model_to_dict(instance))
            changes = {}
            for key, new_val in new_data.items():
                old_val = instance._old_data.get(key)
                if old_val != new_val:
                    changes[key] = {'old': old_val, 'new': new_val}
            
            if not changes: 
                return
                
            changes_str = json.dumps(changes, cls=DjangoJSONEncoder)

        AuditLog.objects.create(
            user=user if user and user.is_authenticated else None,
            action=action,
            model_name=sender.__name__,
            object_id=str(instance.pk),
            object_repr=str(instance)[:250],
            changes=changes_str
        )

@receiver(post_delete)
def audit_post_delete(sender, instance, **kwargs):
    if sender in AUDIT_MODELS:
        user = get_current_user()
        
        AuditLog.objects.create(
            user=user if user and user.is_authenticated else None,
            action='DELETE',
            model_name=sender.__name__,
            object_id=str(instance.pk),
            object_repr=str(instance)[:250],
            changes="Deleted"
        )

from django.contrib.auth import get_user_model
User = get_user_model()
from .models import UserFieldVisibility

@receiver(post_save, sender=User)
def create_user_field_visibility(sender, instance, created, **kwargs):
    if created:
        UserFieldVisibility.objects.create(user=instance)

from django.contrib.auth.signals import user_logged_in
from django.contrib import messages
from .models import SystemSetting
from datetime import datetime

@receiver(user_logged_in)
def check_backup_age_on_login(sender, user, request, **kwargs):
    if user.is_superuser:
        try:
            setting = SystemSetting.objects.get(key='last_backup_date')
            last_backup_date = datetime.fromisoformat(setting.value)
            days_since_backup = (timezone.now() - last_backup_date).days
            if days_since_backup >= 10:
                messages.warning(request, f"It has been {days_since_backup} days since the last system backup. Please download a new backup from the dashboard.")
        except SystemSetting.DoesNotExist:
            messages.warning(request, "A system backup has never been performed. Please download a backup from the dashboard.")
        except Exception:
            pass

