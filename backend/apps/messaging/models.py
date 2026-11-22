from typing import ClassVar

from django.db import models

from apps.accounts.models import Business


class Delivery(models.Model):
    """One row per attempt to send an invoice. Provider webhooks update status (Phase 2)."""

    class Channel(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        EMAIL = "email", "Email"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SHARED = "shared", "Shared"  # click-to-chat: handed to the owner's WhatsApp, unconfirmed
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        READ = "read", "Read"
        FAILED = "failed", "Failed"

    class Kind(models.TextChoices):
        INVOICE = "invoice", "Invoice"
        REMINDER = "reminder", "Reminder"
        QUOTE = "quote", "Quote"

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="deliveries")
    invoice = models.ForeignKey(
        "invoices.Invoice",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    quote = models.ForeignKey(
        "quotes.Quote", null=True, blank=True, on_delete=models.CASCADE, related_name="deliveries"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.INVOICE)
    automatic = models.BooleanField(default=False, help_text="Sent by a scheduled job")
    channel = models.CharField(max_length=10, choices=Channel.choices)
    recipient = models.CharField(max_length=254, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    provider_message_id = models.CharField(max_length=200, blank=True)
    error = models.TextField(blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "deliveries"
        indexes = [models.Index(fields=["provider_message_id"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(invoice__isnull=False) | models.Q(quote__isnull=False),
                name="delivery_has_document",
            )
        ]

    def __str__(self) -> str:
        return f"{self.invoice or self.quote} via {self.channel} to {self.recipient}"

    # Provider statuses only move forward; a late "sent" must not overwrite "read".
    RANK: ClassVar[dict[str, int]] = {
        "queued": 0,
        "shared": 1,
        "sent": 1,
        "delivered": 2,
        "read": 3,
        "failed": 4,
    }

    def advance(self, status: str) -> bool:
        """Move to `status` if it's further along. Returns True if it changed."""
        if self.RANK.get(status, -1) <= self.RANK.get(self.status, -1):
            return False
        self.status = status
        return True


class WebhookEvent(models.Model):
    """Every provider event we've processed, so a redelivered webhook is a no-op."""

    provider = models.CharField(max_length=20)
    event_id = models.CharField(max_length=200)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "event_id"], name="unique_webhook_event")
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.event_id}"
