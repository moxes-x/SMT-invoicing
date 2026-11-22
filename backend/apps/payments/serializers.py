from rest_framework import serializers

from apps.core.serializers import MoneyField

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer[Payment]):
    amount = MoneyField(min_value=1, help_text="Minor units (ngwee).")
    method_label = serializers.CharField(source="get_method_display", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "amount",
            "paid_on",
            "method",
            "method_label",
            "reference",
            "note",
            "created_at",
        ]
        read_only_fields = ["id", "method_label", "created_at"]
