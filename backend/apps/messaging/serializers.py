from rest_framework import serializers

from .models import Delivery


class DeliverySerializer(serializers.ModelSerializer[Delivery]):
    class Meta:
        model = Delivery
        fields = [
            "id",
            "kind",
            "channel",
            "recipient",
            "status",
            "automatic",
            "error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class SendRequestSerializer(serializers.Serializer[object]):
    """How to send. `whatsapp_link` returns a wa.me URL; the others queue a send."""

    channel = serializers.ChoiceField(choices=["whatsapp_link", "whatsapp", "email"])
    to = serializers.EmailField(required=False, help_text="Email only; defaults to the customer's")
    message = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class SendResultSerializer(serializers.Serializer[object]):
    url = serializers.URLField(required=False, help_text="wa.me link (whatsapp_link only)")
    message = serializers.CharField(required=False)
    delivery = DeliverySerializer(required=False)
