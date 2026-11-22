from rest_framework import serializers

from apps.core.serializers import PhoneField

from .models import Customer


class CustomerSerializer(serializers.ModelSerializer[Customer]):
    phone = PhoneField()

    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "address",
            "tpin",
            "notes",
            "language",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
