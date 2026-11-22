from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F

from apps.accounts.models import Business, Currency
from apps.core.money import line_amount, round_half_up
from apps.core.time import today

QUOTE_STATUS_LABELS = {
    "draft": "Draft",
    "sent": "Sent",
    "viewed": "Viewed",
    "accepted": "Accepted",
    "declined": "Declined",
    "expired": "Expired",
    "converted": "Invoiced",
}
QUOTE_DISPLAY_STATUS_CHOICES = list(QUOTE_STATUS_LABELS.items())


class Quote(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        CONVERTED = "converted", "Converted to invoice"

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="quotes")
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="quotes"
    )
    number = models.CharField(max_length=32)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.ZMW)
    issue_date = models.DateField(default=today)
    valid_until = models.DateField()
    notes = models.TextField(blank=True)

    subtotal = models.BigIntegerField(default=0)
    discount_total = models.BigIntegerField(default=0)
    total = models.BigIntegerField(default=0)

    public_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    viewed_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    converted_invoice = models.OneToOneField(
        "invoices.Invoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="quote"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    DOCUMENT_TEMPLATE = "quotes/document.html"

    class Meta:
        ordering = ["-issue_date", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["business", "number"], name="unique_quote_number"),
            models.CheckConstraint(
                condition=models.Q(valid_until__gte=F("issue_date")), name="valid_after_issue"
            ),
        ]

    def __str__(self) -> str:
        return self.number

    @property
    def is_expired(self) -> bool:
        return self.status == self.Status.SENT and self.valid_until < today()

    @property
    def display_status(self) -> str:
        if self.is_expired:
            return "expired"
        if self.status == self.Status.SENT and self.viewed_at:
            return "viewed"
        return self.status

    @property
    def display_status_label(self) -> str:
        return QUOTE_STATUS_LABELS[self.display_status]

    @property
    def is_editable(self) -> bool:
        return self.status in (self.Status.DRAFT, self.Status.SENT)

    @property
    def can_respond(self) -> bool:
        return self.status == self.Status.SENT and not self.is_expired

    def pdf_state(self) -> str:
        return self.display_status

    @property
    def public_path(self) -> str:
        return f"/q/{self.public_token}/"

    @property
    def public_url(self) -> str:
        return settings.PUBLIC_BASE_URL.rstrip("/") + self.public_path


class QuoteLine(models.Model):
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(
        "catalog.Item", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    position = models.PositiveIntegerField(default=0)
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))]
    )
    unit_price = models.BigIntegerField(validators=[MinValueValidator(1)])
    discount = models.BigIntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return self.description

    @property
    def amount(self) -> int:
        return round_half_up(line_amount(self.quantity, self.unit_price, self.discount))
