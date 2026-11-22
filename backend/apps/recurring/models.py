from __future__ import annotations

import calendar
import datetime as dt

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.accounts.models import Business, Currency


def add_months(start: dt.date, months: int) -> dt.date:
    """start + n months, clamped to month end (31 Jan + 1 month = 28/29 Feb)."""
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


class RecurringInvoice(models.Model):
    """A schedule that creates an invoice every N weeks or months."""

    class Frequency(models.TextChoices):
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"

    class SendMode(models.TextChoices):
        DRAFT = "draft", "Create a draft for me to review"
        EMAIL = "email", "Send automatically by email"
        WHATSAPP = "whatsapp", "Send automatically on WhatsApp"

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="recurring")
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="recurring"
    )
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.ZMW)
    frequency = models.CharField(max_length=10, choices=Frequency.choices)
    interval = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    days_until_due = models.PositiveSmallIntegerField(
        default=14, validators=[MaxValueValidator(120)]
    )
    notes = models.TextField(blank=True)
    lines = models.JSONField(
        default=list, help_text="[{item, description, quantity, unit_price, discount}]"
    )
    send_mode = models.CharField(max_length=10, choices=SendMode.choices, default=SendMode.DRAFT)
    is_active = models.BooleanField(default=True)

    runs = models.PositiveIntegerField(default=0, help_text="Invoices generated so far")
    next_run_date = models.DateField()
    last_run_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["next_run_date", "id"]
        indexes = [models.Index(fields=["is_active", "next_run_date"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__isnull=True)
                | models.Q(end_date__gte=models.F("start_date")),
                name="recurring_end_after_start",
            )
        ]

    def __str__(self) -> str:
        return f"{self.customer} every {self.interval} {self.frequency}"

    def occurrence(self, n: int) -> dt.date:
        """The n-th run date (0-based), always computed from start_date so it never drifts."""
        if self.frequency == self.Frequency.WEEKLY:
            return self.start_date + dt.timedelta(weeks=n * self.interval)
        return add_months(self.start_date, n * self.interval)

    @property
    def is_finished(self) -> bool:
        return self.end_date is not None and self.next_run_date > self.end_date
