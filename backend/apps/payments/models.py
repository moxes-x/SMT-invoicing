from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.accounts.models import Business
from apps.core.time import today


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        MTN_MOMO = "mtn_momo", "MTN MoMo"
        AIRTEL_MONEY = "airtel_money", "Airtel Money"
        BANK = "bank", "Bank transfer"
        OTHER = "other", "Other"

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="payments")
    invoice = models.ForeignKey(
        "invoices.Invoice", on_delete=models.PROTECT, related_name="payments"
    )
    amount = models.BigIntegerField(validators=[MinValueValidator(1)], help_text="ngwee")
    paid_on = models.DateField(default=today)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    reference = models.CharField(max_length=100, blank=True)
    note = models.CharField(max_length=300, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_on", "-id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="payment_positive")
        ]

    def __str__(self) -> str:
        return f"{self.invoice} {self.amount}"
