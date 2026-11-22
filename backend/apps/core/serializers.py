from typing import Any

from rest_framework import serializers

from .validators import normalize_phone


class PhoneField(serializers.CharField):
    """Accepts local Zambian or international numbers, stores E.164 (+260971234567)."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("max_length", 32)
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_blank", True)
        super().__init__(**kwargs)

    def to_internal_value(self, data: Any) -> str:
        value = super().to_internal_value(data).strip()
        if not value:
            return ""
        try:
            return normalize_phone(value)
        except Exception as exc:
            raise serializers.ValidationError("Enter a valid phone number.") from exc


class MoneyField(serializers.IntegerField):
    """An amount in minor units (ngwee). K12.50 is sent and returned as 1250."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("min_value", 0)
        kwargs.setdefault("max_value", 10**12)
        super().__init__(**kwargs)
