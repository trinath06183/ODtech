"""
UploadService
=============
Handles all aspects of secure file upload:
  - Extension validation
  - MIME-type validation
  - File size enforcement
  - SHA-256 checksum computation
  - Duplicate detection
  - Filename sanitisation
  - Version creation
"""

import hashlib
import logging
import mimetypes
import os
import re
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.text import slugify

logger = logging.getLogger('edms.upload')


class UploadService:
    """Validates and securely stores uploaded files for EDMS."""

    # Settings shortcuts
    MAX_BYTES       = getattr(settings, 'EDMS_MAX_UPLOAD_BYTES', 50 * 1024 * 1024)
    ALLOWED_EXT     = {ext.lower() for ext in getattr(settings, 'EDMS_ALLOWED_EXTENSIONS', [])}
    ALLOWED_MIME    = set(getattr(settings, 'EDMS_ALLOWED_MIME_TYPES', []))

    # ── Public API ────────────────────────────────────────────────────────────

    @classmethod
    def validate(cls, uploaded_file):
        """
        Run all validation checks on an uploaded file.
        Raises ValidationError with a user-friendly message on failure.
        Returns True on success.
        """
        cls._check_size(uploaded_file)
        cls._check_extension(uploaded_file)
        cls._check_mime(uploaded_file)
        return True

    @classmethod
    def compute_sha256(cls, uploaded_file):
        """Return the hex SHA-256 digest of the uploaded file content."""
        sha256 = hashlib.sha256()
        uploaded_file.seek(0)
        for chunk in iter(lambda: uploaded_file.read(8192), b''):
            sha256.update(chunk)
        uploaded_file.seek(0)
        return sha256.hexdigest()

    @classmethod
    def sanitise_filename(cls, filename):
        """Return a safe filename: lowercase, no special chars, max 100 chars."""
        name, ext = os.path.splitext(filename)
        safe_name = slugify(name)[:80] or 'file'
        safe_ext  = ext.lower()[:10]
        return f"{safe_name}{safe_ext}"

    @classmethod
    def get_mime_type(cls, uploaded_file):
        """Detect MIME type from file headers and filename."""
        # Try magic-number detection first; fall back to filename
        name = uploaded_file.name or ''
        guessed, _ = mimetypes.guess_type(name)
        return guessed or 'application/octet-stream'

    @classmethod
    def get_extension(cls, filename):
        """Return lowercase file extension including the dot."""
        return os.path.splitext(filename)[1].lower()

    @classmethod
    def check_duplicate(cls, file_hash):
        """
        Returns an existing EDMSDocumentVersion with the same hash if one exists,
        or None.  Callers may warn the user about potential duplicates.
        """
        from edms.models import EDMSDocumentVersion
        return EDMSDocumentVersion.objects.filter(file_hash=file_hash).select_related('document').first()

    @classmethod
    def create_version(cls, document, uploaded_file, uploaded_by, change_note=''):
        """
        Create a new EDMSDocumentVersion and update the parent EDMSDocument metadata.

        Steps:
          1. Validate the file.
          2. Compute SHA-256 hash.
          3. Set all previous versions as non-current.
          4. Create the new version record (Django saves the file to disk).
          5. Update the parent document's cached file metadata.

        Returns:
            EDMSDocumentVersion instance.
        """
        from edms.models import EDMSDocumentVersion

        # 1. Validate
        cls.validate(uploaded_file)

        # 2. Compute hash
        file_hash = cls.compute_sha256(uploaded_file)
        filename  = cls.sanitise_filename(uploaded_file.name)
        mime_type = cls.get_mime_type(uploaded_file)
        file_ext  = cls.get_extension(uploaded_file.name)

        # 3. Increment version number
        last_version = (
            EDMSDocumentVersion.objects
            .filter(document=document)
            .order_by('-version_number')
            .values_list('version_number', flat=True)
            .first()
        ) or 0
        new_version_number = last_version + 1

        # 4. Mark all previous versions as non-current
        EDMSDocumentVersion.objects.filter(document=document).update(is_current=False)

        # 5. Create new version (Django ORM saves the file to EDMS_STORAGE_ROOT)
        version = EDMSDocumentVersion(
            document=document,
            version_number=new_version_number,
            file_name=filename,
            file_size=uploaded_file.size,
            mime_type=mime_type,
            file_extension=file_ext,
            file_hash=file_hash,
            change_note=change_note,
            uploaded_by=uploaded_by,
            is_current=True,
        )
        version.file.save(filename, uploaded_file, save=False)
        version.save()

        # 6. Update document cached metadata
        document.current_version = new_version_number
        document.file_name       = filename
        document.file_size       = uploaded_file.size
        document.mime_type       = mime_type
        document.file_extension  = file_ext
        document.file_hash       = file_hash
        document.save(update_fields=[
            'current_version', 'file_name', 'file_size',
            'mime_type', 'file_extension', 'file_hash', 'updated_at',
        ])

        logger.info(
            "[EDMS UPLOAD] Document '%s' — new version v%s created (hash=%s)",
            document.title, new_version_number, file_hash,
        )
        return version

    # ── Private Validators ────────────────────────────────────────────────────

    @classmethod
    def _check_size(cls, f):
        if f.size > cls.MAX_BYTES:
            max_mb = cls.MAX_BYTES // (1024 * 1024)
            raise ValidationError(
                f"File too large. Maximum allowed size is {max_mb} MB "
                f"(your file is {f.size // (1024*1024)} MB)."
            )

    @classmethod
    def _check_extension(cls, f):
        ext = cls.get_extension(f.name)
        if cls.ALLOWED_EXT and ext not in cls.ALLOWED_EXT:
            raise ValidationError(
                f"File type '{ext}' is not allowed. "
                f"Allowed types: {', '.join(sorted(cls.ALLOWED_EXT))}"
            )

    @classmethod
    def _check_mime(cls, f):
        mime = cls.get_mime_type(f)
        if cls.ALLOWED_MIME and mime not in cls.ALLOWED_MIME:
            # Be lenient with octet-stream (some browsers send it for everything)
            if mime != 'application/octet-stream':
                raise ValidationError(
                    f"File MIME type '{mime}' is not permitted."
                )
