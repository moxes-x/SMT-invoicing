from django.apps import AppConfig


class MessagingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.messaging"
    label = "messaging"

    def ready(self) -> None:
        from . import webhooks  # noqa: F401  (connects the anymail tracking receiver)
