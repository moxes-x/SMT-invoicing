from typing import Any

from rest_framework import serializers

from .models import FiscalReceipt, VatCategory, ZraDevice

# ZRA payment methods (pmtTyCd, spec 6.9)
PAYMENT_TYPES = [
    ("01", "Cash"),
    ("02", "Credit (paid later)"),
    ("03", "Cash/credit"),
    ("04", "Bank cheque"),
    ("05", "Card"),
    ("06", "Mobile money"),
    ("07", "Other"),
    ("08", "Bank transfer"),
]


class FiscalReceiptSerializer(serializers.ModelSerializer[FiscalReceipt]):
    class Meta:
        model = FiscalReceipt
        fields = [
            "id",
            "kind",
            "document_number",
            "receipt_no",
            "sdc_id",
            "mrc_no",
            "internal_data",
            "signature",
            "qr_url",
            "signed_at",
            "taxable_total",
            "tax_total",
            "created_at",
        ]
        read_only_fields = fields


class ZraDeviceSerializer(serializers.ModelSerializer[ZraDevice]):
    vat_registered = serializers.BooleanField(source="business.vat_registered", read_only=True)
    tpin = serializers.CharField(source="business.tpin", read_only=True)
    is_ready = serializers.BooleanField(read_only=True)
    default_vat_category = serializers.ChoiceField(choices=VatCategory.choices, required=False)
    payment_type = serializers.ChoiceField(choices=PAYMENT_TYPES, required=False)

    class Meta:
        model = ZraDevice
        fields = [
            "enabled",
            "vsdc_url",
            "branch_id",
            "device_serial",
            "item_class_code",
            "item_type",
            "default_vat_category",
            "payment_type",
            "sdc_id",
            "mrc_no",
            "initialized_at",
            "vat_registered",
            "tpin",
            "is_ready",
        ]
        read_only_fields = ["sdc_id", "mrc_no", "initialized_at"]

    def validate_branch_id(self, value: str) -> str:
        if not (len(value) == 3 and value.isdigit()):
            raise serializers.ValidationError("The branch ID is 3 digits, e.g. 000.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        device = self.instance
        if attrs.get("enabled") and device is not None:
            business = device.business
            if not business.vat_registered:
                raise serializers.ValidationError(
                    {"enabled": "Only VAT-registered businesses issue ZRA tax invoices."}
                )
            if not business.tpin:
                raise serializers.ValidationError(
                    {"enabled": "Add your TPIN in the business details first."}
                )
            for field, label in [
                ("device_serial", "device serial"),
                ("item_class_code", "item class code"),
            ]:
                if not attrs.get(field, getattr(device, field)):
                    raise serializers.ValidationError({field: f"Add the {label} to switch on."})
        return attrs
