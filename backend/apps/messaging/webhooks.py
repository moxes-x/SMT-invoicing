"""Provider webhooks: delivery status updates for WhatsApp and email.

Every webhook is signature-checked and idempotent: an event we've already processed is ignored,
and statuses only ever move forward (a late "sent" can't overwrite "read").
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.dispatch import receiver
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.audit.models import ActivityLog, log

from . import whatsapp
from .models import Delivery, WebhookEvent

logger = logging.getLogger(__name__)

WA_STATUS = {
    "sent": Delivery.Status.SENT,
    "delivered": Delivery.Status.DELIVERED,
    "read": Delivery.Status.READ,
    "failed": Delivery.Status.FAILED,
}


def first_time(provider: str, event_id: str) -> bool:
    """Record the event; False if we've seen it before."""
    try:
        with transaction.atomic():
            WebhookEvent.objects.create(provider=provider, event_id=event_id[:200])
        return True
    except IntegrityError:
        return False


def apply_status(
    provider_message_id: str, status: str, *, error: str = "", provider: str
) -> Delivery | None:
    with transaction.atomic():
        delivery = (
            Delivery.objects.select_for_update()
            .select_related("business")
            .filter(provider_message_id=provider_message_id)
            .first()
        )
        if delivery is None or not delivery.advance(status):
            return delivery
        if error:
            delivery.error = error[:2000]
        delivery.save(update_fields=["status", "error", "updated_at"])
        via = "WhatsApp" if provider == "whatsapp" else "email"
        verb, text = {
            Delivery.Status.DELIVERED: (ActivityLog.Verb.DELIVERED, f"Delivered on {via}"),
            Delivery.Status.READ: (ActivityLog.Verb.READ, f"Read on {via}"),
            Delivery.Status.FAILED: (
                ActivityLog.Verb.DELIVERY_FAILED,
                f"{via.capitalize()} delivery failed" + (f": {error}" if error else ""),
            ),
        }.get(Delivery.Status(status), (None, ""))
        if verb:
            log(
                delivery.business,
                verb,
                text[:300],
                invoice=delivery.invoice_id and delivery.invoice,
                quote=delivery.quote_id and delivery.quote,
            )
        return delivery


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":  # subscription handshake from Meta
        token = request.GET.get("hub.verify_token", "")
        if (
            request.GET.get("hub.mode") == "subscribe"
            and settings.WHATSAPP_VERIFY_TOKEN
            and constant_time_compare(token, settings.WHATSAPP_VERIFY_TOKEN)
        ):
            return HttpResponse(request.GET.get("hub.challenge", ""), content_type="text/plain")
        return HttpResponseForbidden()

    if not whatsapp.verify_signature(request.body, request.headers.get("X-Hub-Signature-256")):
        return HttpResponseForbidden("bad signature")
    try:
        payload: dict[str, Any] = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for st in change.get("value", {}).get("statuses", []):
                message_id, status = st.get("id"), WA_STATUS.get(st.get("status", ""))
                if not message_id or not status:
                    continue
                if not first_time("whatsapp", f"{message_id}:{st.get('status')}"):
                    continue
                errors = st.get("errors") or []
                error = (errors[0].get("title") or errors[0].get("message", "")) if errors else ""
                apply_status(message_id, status, error=error, provider="whatsapp")
    # Always 200 for a valid signature, or Meta keeps retrying.
    return HttpResponse("ok")


# ---- email: anymail normalises every provider's tracking webhook into this signal ------------
try:
    from anymail.signals import tracking

    EMAIL_STATUS = {
        "delivered": Delivery.Status.DELIVERED,
        "opened": Delivery.Status.READ,
        "bounced": Delivery.Status.FAILED,
        "rejected": Delivery.Status.FAILED,
        "failed": Delivery.Status.FAILED,
    }

    @receiver(tracking)
    def on_email_event(sender: Any, event: Any, esp_name: str, **kwargs: Any) -> None:
        status = EMAIL_STATUS.get(event.event_type)
        if not status or not event.message_id:
            return
        event_id = event.event_id or f"{event.message_id}:{event.event_type}"
        if not first_time(f"email:{esp_name}", event_id):
            return
        apply_status(event.message_id, status, error=event.description or "", provider="email")
except ImportError:  # pragma: no cover
    pass
