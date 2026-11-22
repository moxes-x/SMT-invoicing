from typing import Any

from django.conf import settings
from django.db import models

from apps.accounts.models import Business


class ActivityLog(models.Model):
    """Human-readable history, shown as a timeline on each invoice."""

    class Verb(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        SENT = "sent", "Sent"
        SHARED_WHATSAPP = "shared_whatsapp", "Shared via WhatsApp"
        EMAILED = "emailed", "Emailed"
        EMAIL_FAILED = "email_failed", "Email failed"
        VIEWED = "viewed", "Viewed"
        PAYMENT_RECORDED = "payment_recorded", "Payment recorded"
        PAYMENT_DELETED = "payment_deleted", "Payment deleted"
        VOIDED = "voided", "Voided"
        REISSUED = "reissued", "Reissued"
        REMINDED = "reminded", "Reminder sent"
        DELIVERED = "delivered", "Delivered"
        READ = "read", "Read"
        DELIVERY_FAILED = "delivery_failed", "Delivery failed"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        CONVERTED = "converted", "Converted to invoice"
        GENERATED = "generated", "Generated from schedule"

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="activity")
    invoice = models.ForeignKey(
        "invoices.Invoice", null=True, blank=True, on_delete=models.CASCADE, related_name="activity"
    )
    quote = models.ForeignKey(
        "quotes.Quote", null=True, blank=True, on_delete=models.CASCADE, related_name="activity"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    verb = models.CharField(max_length=32, choices=Verb.choices)
    message = models.CharField(max_length=300)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["business", "-created_at"])]

    def __str__(self) -> str:
        return self.message


def log(
    business: Business,
    verb: str,
    message: str,
    *,
    invoice: Any = None,
    quote: Any = None,
    actor: Any = None,
    **data: Any,
) -> ActivityLog:
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None
    return ActivityLog.objects.create(
        business=business,
        invoice=invoice,
        quote=quote,
        actor=actor,
        verb=verb,
        message=message,
        data=data,
    )
