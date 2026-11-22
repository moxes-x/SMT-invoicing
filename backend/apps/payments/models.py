import hashlib
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.accounts.models import Business
from apps.core import crypto
from apps.core.time import today


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        MTN_MOMO = "mtn_momo", "MTN MoMo"
        AIRTEL_MONEY = "airtel_money", "Airtel Money"
        ZAMTEL_KWACHA = "zamtel_kwacha", "Zamtel Kwacha"
        CARD = "card", "Card"
        BANK = "bank", "Bank transfer"
        OTHER = "other", "Other"

    class Source(models.TextChoices):
        MANUAL = "manual", "Recorded by you"
        ONLINE = "online", "Paid online"

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="payments")
    invoice = models.ForeignKey(
        "invoices.Invoice", on_delete=models.PROTECT, related_name="payments"
    )
    amount = models.BigIntegerField(validators=[MinValueValidator(1)], help_text="ngwee")
    paid_on = models.DateField(default=today)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    reference = models.CharField(max_length=100, blank=True)
    note = models.CharField(max_length=300, blank=True)
    receipt_number = models.CharField(max_length=20, blank=True)
    public_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
        return f"{self.receipt_number or self.pk} {self.amount}"

    @property
    def public_path(self) -> str:
        return f"/r/{self.public_token}/"

    @property
    def receipt_url(self) -> str:
        return settings.PUBLIC_BASE_URL.rstrip("/") + self.public_path


class LencoAccount(models.Model):
    """A business's own Lenco (BroadPay) merchant account. Money goes straight to the business;
    this app never holds customer funds."""

    class Environment(models.TextChoices):
        SANDBOX = "sandbox", "Sandbox (test)"
        LIVE = "live", "Live"

    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name="lenco")
    enabled = models.BooleanField(default=False)
    environment = models.CharField(
        max_length=10, choices=Environment.choices, default=Environment.SANDBOX
    )
    public_key = models.CharField(max_length=200, blank=True)
    secret_key_encrypted = models.TextField(blank=True)
    webhook_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Lenco for {self.business}"

    @property
    def secret_key(self) -> str:
        return crypto.decrypt(self.secret_key_encrypted)

    @secret_key.setter
    def secret_key(self, value: str) -> None:
        self.secret_key_encrypted = crypto.encrypt(value)

    @property
    def is_ready(self) -> bool:
        return self.enabled and bool(self.public_key) and bool(self.secret_key)

    @property
    def webhook_hash_key(self) -> str:
        """Lenco signs webhooks with HMAC-SHA512 keyed by the hex SHA-256 of the API secret."""
        return hashlib.sha256(self.secret_key.encode()).hexdigest()

    @property
    def api_url(self) -> str:
        if self.environment == self.Environment.LIVE:
            return str(settings.LENCO_LIVE_API_URL)
        return str(settings.LENCO_SANDBOX_API_URL)

    @property
    def widget_url(self) -> str:
        if self.environment == self.Environment.LIVE:
            return str(settings.LENCO_LIVE_WIDGET_URL)
        return str(settings.LENCO_SANDBOX_WIDGET_URL)

    @property
    def webhook_path(self) -> str:
        return f"/api/webhooks/lenco/{self.webhook_id}/"


class PaymentAttempt(models.Model):
    """One try by a customer to pay an invoice online. Becomes a Payment when Lenco confirms."""

    class Channel(models.TextChoices):
        MOBILE_MONEY = "mobile_money", "Mobile money"
        CARD = "card", "Card"

    class Operator(models.TextChoices):
        MTN = "mtn", "MTN MoMo"
        AIRTEL = "airtel", "Airtel Money"
        ZAMTEL = "zamtel", "Zamtel Kwacha"

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting"
        PAY_OFFLINE = "pay_offline", "Waiting for approval on the phone"
        SUCCESSFUL = "successful", "Paid"
        FAILED = "failed", "Failed"

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="+")
    invoice = models.ForeignKey(
        "invoices.Invoice", on_delete=models.CASCADE, related_name="payment_attempts"
    )
    reference = models.CharField(max_length=64, unique=True)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    operator = models.CharField(max_length=10, choices=Operator.choices, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    amount = models.BigIntegerField(help_text="ngwee requested")
    currency = models.CharField(max_length=3, default="ZMW")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    lenco_reference = models.CharField(max_length=100, blank=True)
    failure_reason = models.CharField(max_length=300, blank=True)
    payment = models.OneToOneField(
        Payment, null=True, blank=True, on_delete=models.SET_NULL, related_name="attempt"
    )
    last_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self) -> str:
        return self.reference

    @property
    def is_open(self) -> bool:
        return self.status in (self.Status.PENDING, self.Status.PAY_OFFLINE)
