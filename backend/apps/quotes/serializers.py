from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.audit.serializers import ActivityLogSerializer
from apps.customers.models import Customer
from apps.invoices.serializers import (
    BusinessScopedPKField,
    CustomerSummarySerializer,
    InvoiceLineSerializer,
    InvoiceRefSerializer,
)
from apps.messaging.serializers import DeliverySerializer

from .models import QUOTE_STATUS_LABELS, Quote, QuoteLine


class QuoteLineSerializer(InvoiceLineSerializer):
    class Meta(InvoiceLineSerializer.Meta):
        model = QuoteLine  # type: ignore[assignment]


class QuoteListSerializer(serializers.ModelSerializer[Quote]):
    customer = CustomerSummarySerializer(read_only=True)
    display_status = serializers.ChoiceField(
        choices=list(QUOTE_STATUS_LABELS.items()), read_only=True
    )

    class Meta:
        model = Quote
        fields = [
            "id",
            "number",
            "status",
            "display_status",
            "customer",
            "currency",
            "issue_date",
            "valid_until",
            "total",
        ]
        read_only_fields = fields


class QuoteSerializer(QuoteListSerializer):
    customer_id = BusinessScopedPKField(
        source="customer", queryset=Customer.objects.all(), write_only=True
    )
    lines = QuoteLineSerializer(many=True)
    is_editable = serializers.BooleanField(read_only=True)
    public_url = serializers.CharField(read_only=True)
    converted_invoice = serializers.SerializerMethodField()
    deliveries = DeliverySerializer(many=True, read_only=True)
    activity = ActivityLogSerializer(many=True, read_only=True)

    class Meta(QuoteListSerializer.Meta):
        fields = [
            *QuoteListSerializer.Meta.fields,
            "customer_id",
            "notes",
            "lines",
            "subtotal",
            "discount_total",
            "is_editable",
            "public_url",
            "sent_at",
            "viewed_at",
            "responded_at",
            "converted_invoice",
            "deliveries",
            "activity",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "number",
            "status",
            "subtotal",
            "discount_total",
            "total",
            "sent_at",
            "viewed_at",
            "responded_at",
        ]

    @extend_schema_field(InvoiceRefSerializer(allow_null=True))
    def get_converted_invoice(self, obj: Quote) -> dict[str, Any] | None:
        inv = obj.converted_invoice
        return {"id": inv.pk, "number": inv.number} if inv else None

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        issue = attrs.get("issue_date") or (self.instance.issue_date if self.instance else None)
        until = attrs.get("valid_until") or (self.instance.valid_until if self.instance else None)
        if issue and until and until < issue:
            raise serializers.ValidationError(
                {"valid_until": "Valid-until can't be before the issue date."}
            )
        if "lines" in attrs and len(attrs["lines"]) > 200:
            raise serializers.ValidationError({"lines": "At most 200 lines per quote."})
        return attrs

    def create(self, validated_data: dict[str, Any]) -> Quote:
        from .services import create_quote

        request = self.context["request"]
        lines = validated_data.pop("lines")
        return create_quote(request.business, request.user, lines=lines, **validated_data)

    def update(self, instance: Quote, validated_data: dict[str, Any]) -> Quote:
        from .services import update_quote

        lines = validated_data.pop("lines", None)
        return update_quote(instance, self.context["request"].user, lines=lines, **validated_data)


class ConvertSerializer(serializers.Serializer[Any]):
    days_until_due = serializers.IntegerField(min_value=0, max_value=120, default=14)


class RespondSerializer(serializers.Serializer[Any]):
    accepted = serializers.BooleanField()
