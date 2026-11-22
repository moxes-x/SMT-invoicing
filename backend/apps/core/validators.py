import phonenumbers
from django.core.exceptions import ValidationError


def normalize_phone(value: str, region: str = "ZM") -> str:
    """Parse a local Zambian or international number and return E.164 (+260971234567)."""
    try:
        parsed = phonenumbers.parse(value, region)
    except phonenumbers.NumberParseException as exc:
        raise ValidationError("Enter a valid phone number.") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise ValidationError("Enter a valid phone number.")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def validate_e164_phone(value: str) -> None:
    if value and normalize_phone(value) != value:
        raise ValidationError("Phone must be stored in E.164 format, e.g. +260971234567.")
