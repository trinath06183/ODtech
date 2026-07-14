import re

from django.core.exceptions import ValidationError

GSTIN_PATTERN = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
)
PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


def normalize_tax_identifier(value):
    return (value or "").replace(" ", "").upper()


def validate_gstin(value):
    normalized = normalize_tax_identifier(value)
    if value and not GSTIN_PATTERN.match(normalized):
        raise ValidationError("Enter a valid GSTIN.")


def validate_pan(value):
    normalized = normalize_tax_identifier(value)
    if value and not PAN_PATTERN.match(normalized):
        raise ValidationError("Enter a valid PAN.")

