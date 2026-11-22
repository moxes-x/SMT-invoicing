from django.conf import settings
from rest_framework import serializers

from apps.core.serializers import MoneyField

from .models import LencoAccount, Payment


class PaymentSerializer(serializers.ModelSerializer[Payment]):
    amount = MoneyField(min_value=1, help_text="Minor units (ngwee).")
    method_label = serializers.CharField(source="get_method_display", read_only=True)
    receipt_url = serializers.CharField(read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "amount",
            "paid_on",
            "method",
            "method_label",
            "source",
            "reference",
            "note",
            "receipt_number",
            "receipt_url",
            "created_at",
        ]
        read_only_fields = ["id", "method_label", "source", "receipt_number", "created_at"]


class LencoAccountSerializer(serializers.ModelSerializer[LencoAccount]):
    secret_key = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        max_length=200,
        help_text="Leave out (or blank) to keep the saved key.",
    )
    has_secret_key = serializers.SerializerMethodField()
    secret_key_hint = serializers.SerializerMethodField()
    webhook_url = serializers.SerializerMethodField()

    class Meta:
        model = LencoAccount
        fields = [
            "enabled",
            "environment",
            "public_key",
            "secret_key",
            "has_secret_key",
            "secret_key_hint",
            "webhook_url",
        ]

    def get_has_secret_key(self, obj: LencoAccount) -> bool:
        return bool(obj.secret_key)

    def get_secret_key_hint(self, obj: LencoAccount) -> str:
        key = obj.secret_key
        return f"…{key[-4:]}" if len(key) >= 8 else ""

    def get_webhook_url(self, obj: LencoAccount) -> str:
        return settings.PUBLIC_BASE_URL.rstrip("/") + obj.webhook_path

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        inst = self.instance
        enabled = attrs.get("enabled", inst.enabled if inst else False)
        public = attrs.get("public_key", inst.public_key if inst else "")
        secret = attrs.get("secret_key") or (inst.secret_key if inst else "")
        if enabled and not public:
            raise serializers.ValidationError({"public_key": "Paste your Lenco public key."})
        if enabled and not secret:
            raise serializers.ValidationError({"secret_key": "Paste your Lenco secret key."})
        return attrs

    def update(self, instance: LencoAccount, validated_data: dict[str, object]) -> LencoAccount:
        secret = validated_data.pop("secret_key", "")
        if secret:
            instance.secret_key = str(secret).strip()
        for k, v in validated_data.items():
            setattr(instance, k, v.strip() if isinstance(v, str) else v)
        instance.save()
        return instance


class ConnectionTestSerializer(serializers.Serializer[object]):
    ok = serializers.BooleanField()
    message = serializers.CharField()
