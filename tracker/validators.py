import os
from django.core.exceptions import ValidationError

def validate_safe_file(value):
    """
    Validates that the uploaded file has a safe extension.
    This prevents upload of executable files, scripts, or other potentially malicious payloads.
    """
    ext = os.path.splitext(value.name)[1].lower()
    # List of safe, commonly used extensions for documents and images
    safe_extensions = [
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.txt',
        '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'
    ]
    
    if ext not in safe_extensions:
        raise ValidationError(f"Unsupported file type '{ext}'. Allowed types: {', '.join(safe_extensions)}")
