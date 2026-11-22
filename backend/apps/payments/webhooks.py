"""Lenco webhook: each business's account posts to its own URL so we know which key signed it."""

from __future__ import annotations

import json
import logging
import uuid

from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.messaging.webhooks import first_time

from . import lenco
from .models import LencoAccount, PaymentAttempt
from .online import apply_collection

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def lenco_webhook(request: HttpRequest, webhook_id: uuid.UUID) -> HttpResponse:
    account = LencoAccount.objects.filter(webhook_id=webhook_id).first()
    if account is None:
        return HttpResponse(status=404)
    if not lenco.verify_signature(
        account, request.body, request.headers.get("X-Lenco-Signature", "")
    ):
        logger.warning("Rejected Lenco webhook with a bad signature for %s", account.business_id)
        return HttpResponse(status=401)
    try:
        payload = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)
    event = str(payload.get("event", ""))
    data = payload.get("data") or {}
    if not event.startswith("collection.") or not isinstance(data, dict):
        return HttpResponse(status=200)  # transfers etc.: not ours to handle
    reference = data.get("reference")
    attempt = PaymentAttempt.objects.filter(
        business=account.business, reference=reference or ""
    ).first()
    if attempt is None:
        # A collection made outside this app (e.g. in Lenco's dashboard). Acknowledge it.
        return HttpResponse(status=200)
    event_id = f"{event}:{data.get('id') or data.get('lencoReference')}:{data.get('status')}"
    if not first_time("lenco", event_id):
        return HttpResponse(status=200)
    if event == "collection.settled":
        return HttpResponse(status=200)  # money moved to the balance; the payment already counts
    apply_collection(attempt, data)
    return HttpResponse(status=200)
