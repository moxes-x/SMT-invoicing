from django.db import models

from apps.accounts.models import Business
from apps.core.validators import validate_e164_phone


class Customer(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="customers")
    name = models.CharField(max_length=200)
    phone = models.CharField(
        max_length=20, blank=True, validators=[validate_e164_phone], help_text="E.164, WhatsApp"
    )
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        indexes = [models.Index(fields=["business", "name"])]

    def __str__(self) -> str:
        return self.name
