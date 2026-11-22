from decimal import Decimal
from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.audit.serializers import ActivityLogSerializer
from apps.catalog.models import Item
from apps.core.serializers import MoneyField
from apps.customers.models import Customer
from apps.payments.serializers import PaymentSerializer

from .models import DISPLAY_STATUS_LABELS, Invoice, InvoiceLine


class BusinessScopedPKField(serializers.PrimaryKeyRelatedField):  # type: ignore[type-arg]
    """A related id that must belong to request.business; others look like they don't exist."""

    def get_queryset(self) -> Any:
        qs: Any = super().get_queryset()
        return qs.filter(business=self.context["request"].business)


class InvoiceLineSerializer(serializers.ModelSerializer[InvoiceLine]):
    item = BusinessScopedPKField(queryset=Item.objects.all(), required=False, allow_null=True)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))
    unit_price = MoneyField(min_value=1, help_text="Minor units (ngwee).")
    discount = MoneyField(required=False, default=0, help_text="Minor units off this line.")
    amount = serializers.IntegerField(read_only=True)

    class Meta:
        model = InvoiceLine
        fields = ["id", "item", "description", "quantity", "unit_price", "discount", "amount"]
        read_only_fields = ["id", "amount"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("discount", 0) > attrs["quantity"] * attrs["unit_price"]:
            raise serializers.ValidationError({"discount": "Discount is more than the line value."})
        return attrs


class CustomerSummarySerializer(serializers.ModelSerializer[Customer]):
    class Meta:
        model = Customer
        fields = ["id", "name", "phone", "email"]


class InvoiceListSerializer(serializers.ModelSerializer[Invoice]):
    customer = CustomerSummarySerializer(read_only=True)
    amount_paid = serializers.IntegerField(read_only=True)
    balance = serializers.IntegerField(read_only=True)
    payment_status = serializers.ChoiceField(choices=Invoice.PaymentStatus.choices, read_only=True)
    display_status = serializers.ChoiceField(
        choices=list(DISPLAY_STATUS_LABELS.items()), read_only=True
    )

    class Meta:
        model = Invoice
        fields = [
            "id",
            "number",
            "status",
            "display_status",
            "payment_status",
            "customer",
            "currency",
            "issue_date",
            "due_date",
            "total",
            "amount_paid",
            "balance",
        ]
        read_only_fields = fields


class InvoiceRefSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    number = serializers.CharField()


class InvoiceSerializer(InvoiceListSerializer):
    customer_id = BusinessScopedPKField(
        source="customer", queryset=Customer.objects.all(), write_only=True
    )
    lines = InvoiceLineSerializer(many=True)
    is_overdue = serializers.SerializerMethodField()
    is_locked = serializers.BooleanField(read_only=True)
    public_url = serializers.CharField(read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    activity = ActivityLogSerializer(many=True, read_only=True)
    reissued_from = serializers.SerializerMethodField()
    reissued_as = serializers.SerializerMethodField()

    class Meta(InvoiceListSerializer.Meta):
        fields = [
            *InvoiceListSerializer.Meta.fields,
            "customer_id",
            "notes",
            "lines",
            "subtotal",
            "discount_total",
            "is_overdue",
            "is_locked",
            "public_url",
            "sent_at",
            "viewed_at",
            "voided_at",
            "void_reason",
            "reissued_from",
            "reissued_as",
            "payments",
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
            "voided_at",
            "void_reason",
        ]

    def get_is_overdue(self, obj: Invoice) -> bool:
        return obj.is_overdue()

    def _ref(self, inv: Invoice | None) -> dict[str, Any] | None:
        return {"id": inv.pk, "number": inv.number} if inv else None

    @extend_schema_field(InvoiceRefSerializer(allow_null=True))
    def get_reissued_from(self, obj: Invoice) -> dict[str, Any] | None:
        return self._ref(obj.reissued_from)

    @extend_schema_field(InvoiceRefSerializer(allow_null=True))
    def get_reissued_as(self, obj: Invoice) -> dict[str, Any] | None:
        return self._ref(getattr(obj, "reissued_as", None))

    def create(self, validated_data: dict[str, Any]) -> Invoice:
        from .services import create_invoice

        request = self.context["request"]
        lines = validated_data.pop("lines")
        return create_invoice(request.business, request.user, lines=lines, **validated_data)

    def update(self, instance: Invoice, validated_data: dict[str, Any]) -> Invoice:
        from .services import update_draft

        lines = validated_data.pop("lines", None)
        return update_draft(instance, self.context["request"].user, lines=lines, **validated_data)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        issue = attrs.get("issue_date") or (self.instance.issue_date if self.instance else None)
        due = attrs.get("due_date") or (self.instance.due_date if self.instance else None)
        if issue and due and due < issue:
            raise serializers.ValidationError({"due_date": "Due date can't be before issue date."})
        if "lines" in attrs and len(attrs["lines"]) > 200:
            raise serializers.ValidationError({"lines": "At most 200 lines per invoice."})
        return attrs


class ReasonSerializer(serializers.Serializer[Any]):
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True)


class EmailRequestSerializer(serializers.Serializer[Any]):
    to = serializers.EmailField(required=False)
    message = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class WhatsAppShareSerializer(serializers.Serializer[Any]):
    url = serializers.URLField()
    message = serializers.CharField()


class DeliverySerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    channel = serializers.CharField()
    recipient = serializers.CharField()
    status = serializers.CharField()


class MoneyByCurrencySerializer(serializers.Serializer[Any]):
    currency = serializers.CharField()
    amount = serializers.IntegerField()
    count = serializers.IntegerField()


class DebtorSerializer(serializers.Serializer[Any]):
    customer_id = serializers.IntegerField()
    name = serializers.CharField()
    currency = serializers.CharField()
    balance = serializers.IntegerField()
    invoices = serializers.IntegerField()


class DashboardSerializer(serializers.Serializer[Any]):
    owed = MoneyByCurrencySerializer(many=True)
    overdue = MoneyByCurrencySerializer(many=True)
    paid_this_month = MoneyByCurrencySerializer(many=True)
    drafts = serializers.IntegerField()
    top_debtors = DebtorSerializer(many=True)
    recent = InvoiceListSerializer(many=True)
