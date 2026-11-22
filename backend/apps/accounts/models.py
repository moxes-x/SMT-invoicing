from __future__ import annotations

from typing import Any, ClassVar

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone

from apps.core.validators import validate_e164_phone


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra: Any) -> User:
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> User:
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> User:
        extra["is_staff"] = True
        extra["is_superuser"] = True
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user that logs in with email. No username field."""

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects: ClassVar[UserManager] = UserManager()  # type: ignore[assignment]

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    def __str__(self) -> str:
        return self.email


class Currency(models.TextChoices):
    ZMW = "ZMW", "Zambian Kwacha"
    USD = "USD", "US Dollar"


tpin_validator = RegexValidator(r"^\d{10}$", "TPIN must be exactly 10 digits.")


class Business(models.Model):
    """The tenant. Every business-owned row in the system points at one of these."""

    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True, validators=[validate_e164_phone])
    address = models.TextField(blank=True)
    tpin = models.CharField("TPIN", max_length=10, blank=True, validators=[tpin_validator])
    vat_registered = models.BooleanField(
        default=False,
        help_text="VAT-registered businesses must issue tax invoices via ZRA Smart Invoice.",
    )
    payment_details = models.TextField(
        blank=True, help_text="Bank / MTN MoMo / Airtel Money details printed on invoices."
    )
    default_currency = models.CharField(
        max_length=3, choices=Currency.choices, default=Currency.ZMW
    )
    # Automatic overdue reminders (sent by the daily Celery beat job).
    auto_reminders = models.BooleanField(default=False)
    reminder_interval_days = models.PositiveSmallIntegerField(
        default=7, validators=[MinValueValidator(1), MaxValueValidator(60)]
    )
    max_reminders = models.PositiveSmallIntegerField(
        default=3, validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    members = models.ManyToManyField(User, through="Membership", related_name="businesses")

    class Meta:
        verbose_name_plural = "businesses"

    def __str__(self) -> str:
        return self.name


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "business"], name="unique_membership"),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.business} ({self.role})"
