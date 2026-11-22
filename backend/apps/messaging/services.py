from __future__ import annotations

from typing import Any
from urllib.parse import quote

from django.db import transaction

from apps.audit.models import ActivityLog, log
from apps.core.money import format_money
from apps.core.queue import enqueue_on_commit
from apps.invoices.models import Invoice
from apps.invoices.services import send_invoice

from .models import Delivery


def invoice_message(invoice: Invoice) -> str:
    amount = format_money(
        invoice.balance if invoice.amount_paid else invoice.total, invoice.currency
    )
    first_name = invoice.customer.name.split()[0] if invoice.customer.name else ""
    greeting = f"Hello {first_name}," if first_name else "Hello,"
    return (
        f"{greeting} here is invoice {invoice.number} from {invoice.business.name} for {amount}, "
        f"due {invoice.due_date:%-d %b %Y}.\n\nView and download it here: {invoice.public_url}"
    )


def whatsapp_link(phone: str, text: str) -> str:
    """wa.me click-to-chat. Without a number WhatsApp lets the owner pick the contact."""
    digits = phone.lstrip("+") if phone else ""
    return f"https://wa.me/{digits}?text={quote(text)}"


@transaction.atomic
def share_via_whatsapp(invoice: Invoice, user: Any) -> dict[str, str]:
    """Phase 1 click-to-chat: free, no Meta approval. We can't confirm delivery; 'viewed' can."""
    invoice = send_invoice(invoice, user)
    phone = invoice.customer.phone
    text = invoice_message(invoice)
    Delivery.objects.create(
        business=invoice.business,
        invoice=invoice,
        channel=Delivery.Channel.WHATSAPP,
        recipient=phone,
        status=Delivery.Status.SHARED,
    )
    log(
        invoice.business,
        ActivityLog.Verb.SHARED_WHATSAPP,
        "Shared via WhatsApp" + (f" to {phone}" if phone else ""),
        invoice=invoice,
        actor=user,
    )
    return {"url": whatsapp_link(phone, text), "message": text}


@transaction.atomic
def queue_email(invoice: Invoice, user: Any, to: str, message: str = "") -> Delivery:
    invoice = send_invoice(invoice, user)
    delivery = Delivery.objects.create(
        business=invoice.business,
        invoice=invoice,
        channel=Delivery.Channel.EMAIL,
        recipient=to,
        status=Delivery.Status.QUEUED,
    )
    from .tasks import send_invoice_email

    enqueue_on_commit(send_invoice_email, delivery.pk, message)
    return delivery
