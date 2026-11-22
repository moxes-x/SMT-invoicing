from django.core.validators import MinValueValidator
from django.db import models

from apps.accounts.models import Business


class Item(models.Model):
    """A saved product or service, to speed up invoice creation."""

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    unit_price = models.BigIntegerField(validators=[MinValueValidator(0)], help_text="ngwee")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return self.name
