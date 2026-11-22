"""Sending invoices, reminders and quotes by WhatsApp (link or Cloud API) and email."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote as urlquote

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.audit.models import ActivityLog, log
from apps.core.money import format_money
from apps.core.queue import enqueue_on_commit
from apps.invoices.models import Invoice
from apps.invoices.services import send_invoice

from . import whatsapp
from .models import Delivery

Kind = Delivery.Kind


def first_name(name: str) -> str:
    return name.split()[0] if name.strip() else ""


def _greeting(doc: Any) -> str:
    name = first_name(doc.customer.name)
    return f"Hello {name}," if name else "Hello,"


def _date(d: dt.date) -> str:
    return f"{d.day} {d:%b %Y}"


def owed(invoice: Invoice) -> int:
    return invoice.balance if invoice.amount_paid else invoice.total


@dataclass
class Content:
    """Everything a channel needs to describe one document."""

    text: str  # click-to-chat / email intro
    params: list[str]  # WhatsApp template body parameters, in order
    headline: str
    amount_label: str
    amount: int
    date_label: str
    date: dt.date
    button_label: str


def content_for(doc: Any, kind: str) -> Content:
    b = doc.business
    if kind == Kind.QUOTE:
        total = format_money(doc.total, doc.currency)
        return Content(
            text=(
                f"{_greeting(doc)} here is quote {doc.number} from {b.name} for {total}, "
                f"valid until {_date(doc.valid_until)}.\n\n"
                f"View it and accept or decline here: {doc.public_url}"
            ),
            params=[
                first_name(doc.customer.name) or "there",
                b.name,
                doc.number,
                total,
                _date(doc.valid_until),
                doc.public_url,
            ],
            headline=f"Quote {doc.number}",
            amount_label="Total",
            amount=doc.total,
            date_label="Valid until",
            date=doc.valid_until,
            button_label="View quote",
        )
    amount = format_money(owed(doc), doc.currency)
    if kind == Kind.REMINDER:
        return Content(
            text=(
                f"{_greeting(doc)} this is a friendly reminder from {b.name} that invoice "
                f"{doc.number} has {amount} outstanding. It was due on {_date(doc.due_date)}.\n\n"
                f"View and download it here: {doc.public_url}"
            ),
            params=[
                first_name(doc.customer.name) or "there",
                b.name,
                doc.number,
                amount,
                _date(doc.due_date),
                doc.public_url,
            ],
            headline=f"Reminder: invoice {doc.number}",
            amount_label="Balance due",
            amount=owed(doc),
            date_label="Was due",
            date=doc.due_date,
            button_label="View invoice",
        )
    return Content(
        text=(
            f"{_greeting(doc)} here is invoice {doc.number} from {b.name} for {amount}, "
            f"due {_date(doc.due_date)}.\n\nView and download it here: {doc.public_url}"
        ),
        params=[
            first_name(doc.customer.name) or "there",
            b.name,
            doc.number,
            amount,
            _date(doc.due_date),
            doc.public_url,
        ],
        headline=f"Invoice {doc.number}",
        amount_label="Amount",
        amount=owed(doc),
        date_label="Due",
        date=doc.due_date,
        button_label="View invoice",
    )


def invoice_message(invoice: Invoice) -> str:
    return content_for(invoice, Kind.INVOICE).text


def whatsapp_link(phone: str, text: str) -> str:
    """wa.me click-to-chat. Without a number WhatsApp lets the owner pick the contact."""
    digits = phone.lstrip("+") if phone else ""
    return f"https://wa.me/{digits}?text={urlquote(text)}"


# ---- preparing the document before it goes out ------------------------------------------------


def _prepare(doc: Any, user: Any, kind: str) -> Any:
    """Make sure the document is in a sendable state; returns the fresh object."""
    if kind == Kind.INVOICE:
        return send_invoice(doc, user)
    if kind == Kind.REMINDER:
        doc = Invoice.objects.with_balance().get(pk=doc.pk)  # type: ignore[attr-defined]
        if doc.status != Invoice.Status.SENT or doc.balance <= 0:
            raise ValidationError({"detail": "Only sent invoices with a balance can be chased."})
        return doc
    from apps.quotes.services import send_quote

    return send_quote(doc, user)


def _doc_fields(doc: Any) -> dict[str, Any]:
    return {"quote": doc} if doc.__class__.__name__ == "Quote" else {"invoice": doc}


def _log_shared(doc: Any, user: Any, kind: str, channel: str, recipient: str) -> None:
    what = {"reminder": "Reminder", "quote": "Quote", "invoice": "Invoice"}[kind]
    verb = ActivityLog.Verb.REMINDED if kind == Kind.REMINDER else ActivityLog.Verb.SHARED_WHATSAPP
    msg = f"{what} shared via WhatsApp" + (f" to {recipient}" if recipient else "")
    if channel != Delivery.Channel.WHATSAPP:
        msg = f"{what} queued for {channel} to {recipient}"
    log(doc.business, verb, msg[:300], actor=user, **_doc_fields(doc))


@transaction.atomic
def share_via_whatsapp(doc: Any, user: Any, kind: str = Kind.INVOICE) -> dict[str, str]:
    """Click-to-chat: free, no Meta approval. We can't confirm delivery; 'viewed' can."""
    doc = _prepare(doc, user, kind)
    phone = doc.customer.phone
    content = content_for(doc, kind)
    Delivery.objects.create(
        business=doc.business,
        kind=kind,
        channel=Delivery.Channel.WHATSAPP,
        recipient=phone,
        status=Delivery.Status.SHARED,
        **_doc_fields(doc),
    )
    _log_shared(doc, user, kind, Delivery.Channel.WHATSAPP, phone)
    return {"url": whatsapp_link(phone, content.text), "message": content.text}


@transaction.atomic
def queue_email(
    doc: Any,
    user: Any,
    to: str,
    message: str = "",
    *,
    kind: str = Kind.INVOICE,
    automatic: bool = False,
) -> Delivery:
    doc = _prepare(doc, user, kind)
    delivery = Delivery.objects.create(
        business=doc.business,
        kind=kind,
        automatic=automatic,
        channel=Delivery.Channel.EMAIL,
        recipient=to,
        status=Delivery.Status.QUEUED,
        **_doc_fields(doc),
    )
    from .tasks import send_delivery

    enqueue_on_commit(send_delivery, delivery.pk, message)
    return delivery


@transaction.atomic
def queue_whatsapp(
    doc: Any, user: Any, *, kind: str = Kind.INVOICE, automatic: bool = False
) -> Delivery:
    """Send through the WhatsApp Cloud API from the platform number (template + PDF)."""
    if not whatsapp.is_enabled():
        raise ValidationError({"detail": "Automatic WhatsApp isn't set up on this server."})
    if not doc.customer.phone:
        raise ValidationError({"detail": "This customer has no WhatsApp number."})
    doc = _prepare(doc, user, kind)
    delivery = Delivery.objects.create(
        business=doc.business,
        kind=kind,
        automatic=automatic,
        channel=Delivery.Channel.WHATSAPP,
        recipient=doc.customer.phone,
        status=Delivery.Status.QUEUED,
        **_doc_fields(doc),
    )
    from .tasks import send_delivery

    enqueue_on_commit(send_delivery, delivery.pk, "")
    return delivery


def best_channel(doc: Any) -> str | None:
    """For automatic sends: WhatsApp API if possible, else email, else nothing."""
    if whatsapp.is_enabled() and doc.customer.phone:
        return Delivery.Channel.WHATSAPP
    if doc.customer.email:
        return Delivery.Channel.EMAIL
    return None


def send_automatically(doc: Any, *, kind: str, channel: str | None = None) -> Delivery | None:
    channel = channel or best_channel(doc)
    if channel == Delivery.Channel.WHATSAPP and whatsapp.is_enabled() and doc.customer.phone:
        return queue_whatsapp(doc, None, kind=kind, automatic=True)
    if channel == Delivery.Channel.EMAIL and doc.customer.email:
        return queue_email(doc, None, doc.customer.email, kind=kind, automatic=True)
    return None


def dispatch(doc: Any, user: Any, kind: str, data: dict[str, Any]) -> dict[str, Any]:
    """Handle a validated SendRequestSerializer payload for any document kind."""
    from .serializers import DeliverySerializer

    channel = data["channel"]
    if channel == "whatsapp_link":
        return share_via_whatsapp(doc, user, kind)
    if channel == "whatsapp":
        return {"delivery": DeliverySerializer(queue_whatsapp(doc, user, kind=kind)).data}
    to = data.get("to") or doc.customer.email
    if not to:
        raise ValidationError({"to": "This customer has no email address. Enter one."})
    delivery = queue_email(doc, user, to, data.get("message", ""), kind=kind)
    return {"delivery": DeliverySerializer(delivery).data}
