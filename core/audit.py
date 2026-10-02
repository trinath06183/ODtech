"""
core/audit.py
=============
Provides signal-based, field-level audit logging for Django models.

Usage — register a model for tracking:
    from core.audit import register_audit

    register_audit(
        MyModel,
        track_fields=['name', 'amount', 'status'],   # Only these fields tracked
        label_field='__str__',                        # Used as object_repr
    )

The AuditLog records are stored in core.AuditLog with old_values / new_values
as JSON, along with the user (extracted from the current request via thread-local)
and IP address.
"""

import threading
import logging
from decimal import Decimal
from datetime import date, datetime

from django.db import models
from django.contrib.contenttypes.models import ContentType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread-local storage — set by middleware so signals can access the user/ip
# ---------------------------------------------------------------------------
_request_local = threading.local()


def get_current_user():
    return getattr(_request_local, 'user', None)


def get_current_ip():
    return getattr(_request_local, 'ip', None)


def set_current_request(user, ip):
    _request_local.user = user
    _request_local.ip = ip


# ---------------------------------------------------------------------------
# Value serializer — converts Python values to JSON-safe primitives
# ---------------------------------------------------------------------------
def _serialize_value(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, models.Model):
        return str(value.pk)
    try:
        return str(value)
    except Exception:
        return repr(value)


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------
def _snapshot(instance, fields):
    """Return a dict of current field values for the given field names."""
    snap = {}
    for field_name in fields:
        try:
            value = getattr(instance, field_name)
            # For FK fields, store the PK not the object
            if hasattr(value, 'pk'):
                value = value.pk
            snap[field_name] = _serialize_value(value)
        except Exception:
            snap[field_name] = None
    return snap


def _diff(old, new):
    """Return only fields that actually changed."""
    changed_old = {}
    changed_new = {}
    for k in new:
        if old.get(k) != new.get(k):
            changed_old[k] = old.get(k)
            changed_new[k] = new.get(k)
    return changed_old, changed_new


# ---------------------------------------------------------------------------
# AuditLog writer
# ---------------------------------------------------------------------------
def _write_log(action, instance, old_values=None, new_values=None, label=None):
    from core.models import AuditLog  # lazy import to avoid circular deps
    try:
        ct = ContentType.objects.get_for_model(instance.__class__)
        AuditLog.objects.create(
            user=get_current_user(),
            ip_address=get_current_ip(),
            action=action,
            content_type=ct,
            object_id=str(instance.pk),
            object_repr=label or str(instance)[:255],
            old_values=old_values,
            new_values=new_values,
        )
    except Exception as e:
        logger.error(f"[AuditLog] Failed to write log for {instance}: {e}")


# ---------------------------------------------------------------------------
# Signal handlers factory
# ---------------------------------------------------------------------------
def _make_pre_save_handler(track_fields):
    def pre_save_handler(sender, instance, **kwargs):
        if instance.pk:
            # Existing object — capture old state from DB
            try:
                old_instance = sender.objects.get(pk=instance.pk)
                instance._audit_old = _snapshot(old_instance, track_fields)
            except sender.DoesNotExist:
                instance._audit_old = {}
        else:
            instance._audit_old = None  # New object
    return pre_save_handler


def _make_post_save_handler(track_fields):
    def post_save_handler(sender, instance, created, **kwargs):
        new_snap = _snapshot(instance, track_fields)
        label = str(instance)[:255]

        if created:
            _write_log(
                action='CREATE',
                instance=instance,
                old_values=None,
                new_values=new_snap,
                label=label,
            )
        else:
            old_snap = getattr(instance, '_audit_old', {}) or {}
            old_diff, new_diff = _diff(old_snap, new_snap)
            if old_diff or new_diff:  # Only log if something actually changed
                _write_log(
                    action='UPDATE',
                    instance=instance,
                    old_values=old_diff,
                    new_values=new_diff,
                    label=label,
                )
    return post_save_handler


def _make_post_delete_handler(track_fields):
    def post_delete_handler(sender, instance, **kwargs):
        snap = _snapshot(instance, track_fields)
        _write_log(
            action='DELETE',
            instance=instance,
            old_values=snap,
            new_values=None,
            label=str(instance)[:255],
        )
    return post_delete_handler


# ---------------------------------------------------------------------------
# Public API: register_audit()
# ---------------------------------------------------------------------------
_registered_models = set()


def register_audit(model, track_fields, label_field=None):
    """
    Register a Django model for field-level audit tracking.

    Args:
        model:         The Django model class to track.
        track_fields:  List of field names to include in change snapshots.
        label_field:   (unused — __str__ is always used for object_repr)
    """
    if model in _registered_models:
        return
    _registered_models.add(model)

    models.signals.pre_save.connect(_make_pre_save_handler(track_fields), sender=model, weak=False)
    models.signals.post_save.connect(_make_post_save_handler(track_fields), sender=model, weak=False)
    models.signals.post_delete.connect(_make_post_delete_handler(track_fields), sender=model, weak=False)
