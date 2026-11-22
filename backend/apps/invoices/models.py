from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from apps.accounts.models import Business, Currency
from apps.core.money import line_amount, round_half_up
from apps.core.time import today

DISPLAY_STATUS_LABELS = {
    "draft": "Draft",
    "sent": "Sent",
    "viewed": "Viewed",
    "partial": "Partly paid",
    "paid": "Paid",
    "overdue": "Overdue",
    "void": "Void",
}

DISPLAY_STATUS_CHOICES = list(DISPLAY_STATUS_LABELS.items())


class InvoiceQuerySet(models.QuerySet["Invoice"]):
    def with_balance(self) -> InvoiceQuerySet:
        """Annotate amount_paid / balance in SQL (a subquery, so no join fan-out)."""
        from apps.payments.models import Payment

        paid = (
            Payment.objects.filter(invoice=OuterRef("pk"))
            .values("invoice")
            .annotate(s=Sum("amount"))
            .values("s")
        )
        return self.annotate(
            paid_amount=Coalesce(Subquery(paid, output_field=models.BigIntegerField()), Value(0))
        ).annotate(balance_amount=F("total") - F("paid_amount"))

    def outstanding(self) -> InvoiceQuerySet:
        qs: Any = self.with_balance()  # annotations aren't visible to django-stubs
        return qs.filter(status=Invoice.Status.SENT, balance_amount__gt=0)  # type: ignore[no-any-return]

    def overdue(self, on: dt.date | None = None) -> InvoiceQuerySet:
        return self.outstanding().filter(due_date__lt=on or today())


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        VOID = "void", "Void"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PARTIAL = "partial", "Partly paid"
        PAID = "paid", "Paid"

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="invoices")
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="invoices"
    )
    number = models.CharField(max_length=32)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.ZMW)
    issue_date = models.DateField(default=today)
    due_date = models.DateField()
    notes = models.TextField(blank=True)

    # Computed server-side from the lines; never accepted from the client.
    subtotal = models.BigIntegerField(default=0)
    discount_total = models.BigIntegerField(default=0)
    total = models.BigIntegerField(default=0)

    public_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    viewed_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=300, blank=True)
    recurring = models.ForeignKey(
        "recurring.RecurringInvoice",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invoices",
    )
    reminders_paused = models.BooleanField(
        default=False, help_text="Skip automatic reminders for this invoice."
    )
    reissued_from = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="reissued_as"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = InvoiceQuerySet.as_manager()

    DOCUMENT_TEMPLATE = "invoices/document.html"

    class Meta:
        ordering = ["-issue_date", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["business", "number"], name="unique_invoice_number"),
            models.CheckConstraint(
                condition=models.Q(due_date__gte=F("issue_date")), name="due_after_issue"
            ),
            # A schedule produces at most one invoice per run date, even if the job runs twice.
            models.UniqueConstraint(
                fields=["recurring", "issue_date"],
                condition=models.Q(recurring__isnull=False),
                name="one_invoice_per_recurring_run",
            ),
        ]
        indexes = [models.Index(fields=["business", "status", "due_date"])]

    def __str__(self) -> str:
        return self.number

    # --- derived payment state -------------------------------------------------------------
    @property
    def amount_paid(self) -> int:
        annotated = getattr(self, "paid_amount", None)
        if annotated is not None:
            return int(annotated)
        return int(self.payments.aggregate(s=Sum("amount"))["s"] or 0)  # type: ignore[attr-defined]

    @property
    def balance(self) -> int:
        return self.total - self.amount_paid

    @property
    def payment_status(self) -> str:
        paid = self.amount_paid
        if paid <= 0:
            return self.PaymentStatus.UNPAID
        if paid < self.total:
            return self.PaymentStatus.PARTIAL
        return self.PaymentStatus.PAID

    def is_overdue(self, on: dt.date | None = None) -> bool:
        return (
            self.status == self.Status.SENT and self.balance > 0 and self.due_date < (on or today())
        )

    @property
    def display_status(self) -> str:
        """One label for badges: draft, void, paid, overdue, partial, viewed or sent."""
        if self.status != self.Status.SENT:
            return self.status
        ps = self.payment_status
        if ps == self.PaymentStatus.PAID:
            return "paid"
        if self.is_overdue():
            return "overdue"
        if ps == self.PaymentStatus.PARTIAL:
            return "partial"
        return "viewed" if self.viewed_at else "sent"

    @property
    def display_status_label(self) -> str:
        return DISPLAY_STATUS_LABELS[self.display_status]

    @property
    def is_locked(self) -> bool:
        return self.status != self.Status.DRAFT

    def pdf_state(self) -> str:
        return f"{self.amount_paid}|{self.display_status}"

    @property
    def public_path(self) -> str:
        return f"/i/{self.public_token}/"

    @property
    def public_url(self) -> str:
        return settings.PUBLIC_BASE_URL.rstrip("/") + self.public_path


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(
        "catalog.Item", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    position = models.PositiveIntegerField(default=0)
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))]
    )
    unit_price = models.BigIntegerField(validators=[MinValueValidator(1)], help_text="ngwee")
    discount = models.BigIntegerField(
        default=0, validators=[MinValueValidator(0)], help_text="ngwee off this line"
    )

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.description

    @property
    def amount(self) -> int:
        return round_half_up(line_amount(self.quantity, self.unit_price, self.discount))


class InvoiceSequence(models.Model):
    """Per-business, per-prefix, per-year counter (INV, QUO…).

    Locked with SELECT ... FOR UPDATE when allocating.
    """

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="+")
    prefix = models.CharField(max_length=8, default="INV")
    year = models.PositiveIntegerField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["business", "prefix", "year"], name="unique_sequence_prefix_year"
            )
        ]

    def __str__(self) -> str:
        return f"{self.business_id}/{self.prefix}/{self.year}: {self.last_number}"
