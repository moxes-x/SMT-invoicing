from rest_framework import serializers

from .models import ActivityLog


class ActivityLogSerializer(serializers.ModelSerializer[ActivityLog]):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = ["id", "verb", "message", "actor_name", "created_at"]

    def get_actor_name(self, obj: ActivityLog) -> str | None:
        if obj.actor is None:
            return None
        return obj.actor.full_name or obj.actor.email  # type: ignore[attr-defined]
