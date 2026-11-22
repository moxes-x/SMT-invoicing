from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Business
from apps.audit.models import ActivityLog, log
from apps.invoices.models import Invoice
from apps.invoices.services import LineData, copy_lines, create_invoice, next_number, write_lines

from .models import Quote


def _user(user: Any) -> Any:
    return user if getattr(user, "is_authenticated", False) else None


@transaction.atomic
def create_quote(
    business: Business, user: Any, *, lines: Sequence[LineData], **fields: Any
) -> Quote:
    issue_date = fields.get("issue_date") or timezone.localdate()
    fields["issue_date"] = issue_date
    fields.setdefault("currency", business.default_currency)
    quote = Quote(
        business=business,
        created_by=_user(user),
        number=next_number(business, issue_date.year, prefix="QUO"),
        **fields,
    )
    quote.save()
    write_lines(quote, lines)
    quote.save(update_fields=["subtotal", "discount_total", "total", "updated_at"])
    log(business, ActivityLog.Verb.CREATED, "Quote created", quote=quote, actor=user)
    return quote


def _lock(quote: Quote) -> Quote:
    return Quote.objects.select_for_update().get(pk=quote.pk)


@transaction.atomic
def update_quote(
    quote: Quote, user: Any, *, lines: Sequence[LineData] | None = None, **fields: Any
) -> Quote:
    quote = _lock(quote)
    if not quote.is_editable:
        raise ValidationError({"detail": "This quote has been answered and can't be edited."})
    for field, value in fields.items():
        setattr(quote, field, value)
    if lines is not None:
        write_lines(quote, lines)
    quote.save()
    if quote.status == Quote.Status.SENT:
        log(quote.business, ActivityLog.Verb.UPDATED, "Quote updated", quote=quote, actor=user)
    return quote


@transaction.atomic
def send_quote(quote: Quote, user: Any) -> Quote:
    quote = _lock(quote)
    if quote.status == Quote.Status.SENT:
        return quote
    if quote.status != Quote.Status.DRAFT:
        raise ValidationError({"detail": "This quote has already been answered."})
    if not quote.lines.exists() or quote.total <= 0:  # type: ignore[attr-defined]
        raise ValidationError({"detail": "Add at least one line before sending."})
    quote.status = Quote.Status.SENT
    quote.sent_at = timezone.now()
    quote.save(update_fields=["status", "sent_at", "updated_at"])
    log(quote.business, ActivityLog.Verb.SENT, "Quote marked as sent", quote=quote, actor=user)
    return quote


@transaction.atomic
def respond(quote: Quote, accepted: bool, user: Any = None) -> Quote:
    """Customer (public link) or owner records the answer."""
    quote = _lock(quote)
    if not quote.can_respond:
        raise ValidationError({"detail": "This quote can no longer be accepted or declined."})
    quote.status = Quote.Status.ACCEPTED if accepted else Quote.Status.DECLINED
    quote.responded_at = timezone.now()
    quote.save(update_fields=["status", "responded_at", "updated_at"])
    who = "by customer" if user is None else ""
    if accepted:
        log(
            quote.business,
            ActivityLog.Verb.ACCEPTED,
            f"Accepted {who}".strip(),
            quote=quote,
            actor=user,
        )
    else:
        log(
            quote.business,
            ActivityLog.Verb.DECLINED,
            f"Declined {who}".strip(),
            quote=quote,
            actor=user,
        )
    return quote


@transaction.atomic
def convert_to_invoice(quote: Quote, user: Any, *, days_until_due: int = 14) -> Invoice:
    quote = _lock(quote)
    if quote.status == Quote.Status.CONVERTED:
        raise ValidationError({"detail": "This quote was already turned into an invoice."})
    if quote.status == Quote.Status.DECLINED:
        raise ValidationError({"detail": "This quote was declined."})
    today = timezone.localdate()
    invoice = create_invoice(
        quote.business,
        user,
        lines=copy_lines(quote),
        customer=quote.customer,
        currency=quote.currency,
        issue_date=today,
        due_date=today + dt.timedelta(days=days_until_due),
        notes=quote.notes,
    )
    quote.status = Quote.Status.CONVERTED
    quote.converted_invoice = invoice
    quote.save(update_fields=["status", "converted_invoice", "updated_at"])
    log(
        quote.business,
        ActivityLog.Verb.CONVERTED,
        f"Converted to invoice {invoice.number}",
        quote=quote,
        actor=user,
    )
    log(
        quote.business,
        ActivityLog.Verb.CREATED,
        f"Created from quote {quote.number}",
        invoice=invoice,
        actor=user,
    )
    return invoice


def mark_viewed(quote: Quote) -> None:
    if Quote.objects.filter(pk=quote.pk, viewed_at__isnull=True).update(viewed_at=timezone.now()):
        log(quote.business, ActivityLog.Verb.VIEWED, "Viewed by customer", quote=quote)
