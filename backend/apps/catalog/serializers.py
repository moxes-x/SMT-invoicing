from rest_framework import serializers

from apps.core.serializers import MoneyField

from .models import Item


class ItemSerializer(serializers.ModelSerializer[Item]):
    unit_price = MoneyField(help_text="Minor units (ngwee).")

    class Meta:
        model = Item
        fields = [
            "id",
            "name",
            "description",
            "unit_price",
            "vat_category",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
