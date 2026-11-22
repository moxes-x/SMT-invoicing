import datetime as dt
from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.core.money import invoice_totals
from apps.core.time import today
from apps.customers.models import Customer
from apps.invoices.serializers import BusinessScopedPKField, CustomerSummarySerializer

from .models import RecurringInvoice
from .services import preview_dates


class RecurringLineSerializer(serializers.Serializer[Any]):
    """Same rules as an invoice line; stored as JSON on the schedule."""

    item = serializers.IntegerField(required=False, allow_null=True)
    description = serializers.CharField(max_length=500)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))
    unit_price = serializers.IntegerField(min_value=1, max_value=10**12)
    discount = serializers.IntegerField(min_value=0, max_value=10**12, default=0)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("discount", 0) > attrs["quantity"] * attrs["unit_price"]:
            raise serializers.ValidationError({"discount": "Discount is more than the line value."})
        return attrs


class RecurringInvoiceSerializer(serializers.ModelSerializer[RecurringInvoice]):
    customer = CustomerSummarySerializer(read_only=True)
    customer_id = BusinessScopedPKField(
        source="customer", queryset=Customer.objects.all(), write_only=True
    )
    lines = RecurringLineSerializer(many=True)
    total = serializers.SerializerMethodField()
    upcoming = serializers.SerializerMethodField()
    invoice_count = serializers.SerializerMethodField()

    class Meta:
        model = RecurringInvoice
        fields = [
            "id",
            "customer",
            "customer_id",
            "currency",
            "frequency",
            "interval",
            "start_date",
            "end_date",
            "days_until_due",
            "notes",
            "lines",
            "send_mode",
            "is_active",
            "next_run_date",
            "runs",
            "last_run_at",
            "total",
            "upcoming",
            "invoice_count",
            "created_at",
        ]
        read_only_fields = ["id", "next_run_date", "runs", "last_run_at", "created_at"]

    def get_total(self, obj: RecurringInvoice) -> int:
        return invoice_totals(
            (
                Decimal(str(line["quantity"])),
                int(line["unit_price"]),
                int(line.get("discount") or 0),
            )
            for line in obj.lines
        )["total"]

    def get_upcoming(self, obj: RecurringInvoice) -> list[dt.date]:
        return preview_dates(obj) if obj.is_active else []

    def get_invoice_count(self, obj: RecurringInvoice) -> int:
        return obj.invoices.count()  # type: ignore[attr-defined]

    def validate_lines(self, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not lines:
            raise serializers.ValidationError("Add at least one line.")
        if len(lines) > 200:
            raise serializers.ValidationError("At most 200 lines.")
        business = self.context["request"].business
        from apps.catalog.models import Item

        ids = {line["item"] for line in lines if line.get("item")}
        if ids and Item.objects.filter(business=business, pk__in=ids).count() != len(ids):
            raise serializers.ValidationError("Unknown item.")
        # JSON-safe: quantities as strings so no float ever touches money.
        return [{**line, "quantity": str(line["quantity"])} for line in lines]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        inst = self.instance
        start = attrs.get("start_date", inst.start_date if inst else None)
        end = attrs.get("end_date", inst.end_date if inst else None)
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "End date can't be before the start."})
        if inst is None and start and start < today():
            raise serializers.ValidationError({"start_date": "Start today or later."})
        return attrs

    def create(self, validated_data: dict[str, Any]) -> RecurringInvoice:
        request = self.context["request"]
        return RecurringInvoice.objects.create(
            business=request.business,
            created_by=request.user,
            next_run_date=validated_data["start_date"],
            **validated_data,
        )

    def update(
        self, instance: RecurringInvoice, validated_data: dict[str, Any]
    ) -> RecurringInvoice:
        schedule_changed = any(
            k in validated_data and validated_data[k] != getattr(instance, k)
            for k in ("frequency", "interval", "start_date")
        )
        resumed = validated_data.get("is_active") is True and not instance.is_active
        instance = super().update(instance, validated_data)
        if schedule_changed or resumed:
            # Restart from the start (or carry on after a pause), skipping dates in the past:
            # nobody wants a pile of back-dated invoices for the weeks it was paused.
            instance.runs = 0 if schedule_changed else instance.runs
            while instance.occurrence(instance.runs) < today():
                instance.runs += 1
            instance.next_run_date = instance.occurrence(instance.runs)
            instance.save(update_fields=["runs", "next_run_date", "updated_at"])
        return instance
