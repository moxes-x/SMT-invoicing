"""Invoice business rules. Views stay thin; everything that changes an invoice goes through here."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from decimal import Decimal
from typing import Any, TypedDict

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Business
from apps.audit.models import ActivityLog, log
from apps.core.money import format_money, invoice_totals
from apps.core.queue import enqueue_on_commit

from .models import Invoice, InvoiceSequence


class InvoiceLocked(ValidationError):
    default_detail = "Sent invoices can't be edited. Void it and reissue instead."
    default_code = "invoice_locked"


class LineData(TypedDict, total=False):
    item: Any
    description: str
    quantity: Decimal
    unit_price: int
    discount: int


def next_number(business: Business, year: int, prefix: str = "INV") -> str:
    """Allocate <prefix>-<year>-<nnnn>. Must run inside the caller's transaction.

    The row is created if missing (ON CONFLICT DO NOTHING, so racing creators don't error) and then
    locked with SELECT ... FOR UPDATE, so concurrent callers queue and never share a number.
    """
    InvoiceSequence.objects.bulk_create(
        [InvoiceSequence(business=business, prefix=prefix, year=year)], ignore_conflicts=True
    )
    seq = InvoiceSequence.objects.select_for_update().get(
        business=business, prefix=prefix, year=year
    )
    seq.last_number += 1
    seq.save(update_fields=["last_number"])
    return f"{prefix}-{year}-{seq.last_number:04d}"


def write_lines(doc: Any, lines: Sequence[LineData]) -> None:
    """Replace an invoice's or quote's lines and recompute its totals (doc must be saved)."""
    manager = doc.lines
    model, fk = manager.model, manager.field.name
    manager.all().delete()
    model.objects.bulk_create(
        model(**{fk: doc}, position=i, **line) for i, line in enumerate(lines)
    )
    totals = invoice_totals(
        (Decimal(line["quantity"]), int(line["unit_price"]), int(line.get("discount", 0)))
        for line in lines
    )
    for field, value in totals.items():
        setattr(doc, field, value)


def copy_lines(doc: Any) -> list[LineData]:
    return [
        {
            "item": line.item,
            "description": line.description,
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "discount": line.discount,
        }
        for line in doc.lines.all()
    ]


@transaction.atomic
def create_invoice(
    business: Business, user: Any, *, lines: Sequence[LineData], **fields: Any
) -> Invoice:
    issue_date: dt.date = fields.get("issue_date") or timezone.localdate()
    fields["issue_date"] = issue_date
    fields.setdefault("currency", business.default_currency)
    invoice = Invoice(
        business=business,
        created_by=user if getattr(user, "is_authenticated", False) else None,
        number=next_number(business, issue_date.year),
        **fields,
    )
    invoice.save()
    write_lines(invoice, lines)
    invoice.save(update_fields=["subtotal", "discount_total", "total", "updated_at"])
    log(business, ActivityLog.Verb.CREATED, "Created as draft", invoice=invoice, actor=user)
    return invoice


def _lock(invoice: Invoice) -> Invoice:
    return Invoice.objects.select_for_update().get(pk=invoice.pk)


@transaction.atomic
def update_draft(
    invoice: Invoice, user: Any, *, lines: Sequence[LineData] | None = None, **fields: Any
) -> Invoice:
    invoice = _lock(invoice)
    if invoice.is_locked:
        raise InvoiceLocked()
    for field, value in fields.items():
        setattr(invoice, field, value)
    if lines is not None:
        write_lines(invoice, lines)
    invoice.save()
    return invoice


@transaction.atomic
def send_invoice(invoice: Invoice, user: Any) -> Invoice:
    """draft → sent. Idempotent for an already-sent invoice."""
    invoice = _lock(invoice)
    if invoice.status == Invoice.Status.SENT:
        return invoice
    if invoice.status == Invoice.Status.VOID:
        raise ValidationError({"detail": "A void invoice can't be sent."})
    if not invoice.lines.exists():  # type: ignore[attr-defined]
        raise ValidationError({"detail": "Add at least one line before sending."})
    if invoice.total <= 0:
        raise ValidationError({"detail": "The invoice total must be more than zero."})
    invoice.status = Invoice.Status.SENT
    invoice.sent_at = timezone.now()
    invoice.save(update_fields=["status", "sent_at", "updated_at"])
    log(invoice.business, ActivityLog.Verb.SENT, "Marked as sent", invoice=invoice, actor=user)

    from .tasks import build_invoice_pdf

    enqueue_on_commit(build_invoice_pdf, invoice.pk)
    return invoice


@transaction.atomic
def void_invoice(invoice: Invoice, user: Any, reason: str = "") -> Invoice:
    invoice = _lock(invoice)
    if invoice.status == Invoice.Status.VOID:
        raise ValidationError({"detail": "This invoice is already void."})
    if invoice.payments.exists():  # type: ignore[attr-defined]
        raise ValidationError(
            {
                "detail": "This invoice has payments. Delete them before voiding, "
                "so the record stays honest."
            }
        )
    invoice.status = Invoice.Status.VOID
    invoice.voided_at = timezone.now()
    invoice.void_reason = reason
    invoice.save(update_fields=["status", "voided_at", "void_reason", "updated_at"])
    msg = "Voided" + (f": {reason}" if reason else "")
    log(invoice.business, ActivityLog.Verb.VOIDED, msg[:300], invoice=invoice, actor=user)
    return invoice


@transaction.atomic
def reissue_invoice(invoice: Invoice, user: Any, reason: str = "") -> Invoice:
    """Void a sent invoice and open an editable draft copy with a new number."""
    original = _lock(invoice)
    if original.status == Invoice.Status.DRAFT:
        raise ValidationError({"detail": "Drafts can be edited directly."})
    if hasattr(original, "reissued_as"):
        raise ValidationError({"detail": "This invoice was already reissued."})
    if original.status != Invoice.Status.VOID:
        original = void_invoice(original, user, reason or "Reissued")
    lines = copy_lines(original)
    today = timezone.localdate()
    term = original.due_date - original.issue_date
    copy = create_invoice(
        original.business,
        user,
        lines=lines,
        customer=original.customer,
        currency=original.currency,
        issue_date=today,
        due_date=today + term,
        notes=original.notes,
        reissued_from=original,
    )
    log(
        original.business,
        ActivityLog.Verb.REISSUED,
        f"Reissued as {copy.number}",
        invoice=original,
        actor=user,
    )
    log(
        copy.business,
        ActivityLog.Verb.REISSUED,
        f"Replaces {original.number}",
        invoice=copy,
        actor=user,
    )
    return copy


@transaction.atomic
def record_payment(invoice: Invoice, user: Any, *, online: bool = False, **data: Any) -> Any:
    """Record money received. Every payment gets a receipt number (RCT-<year>-<nnnn>).

    Online payments skip the balance check: the money has already arrived (e.g. the customer paid
    twice), so it must be recorded; the timeline flags the overpayment for a refund.
    """
    from apps.payments.models import Payment

    invoice = _lock(invoice)
    if invoice.status != Invoice.Status.SENT and not online:
        raise ValidationError({"detail": "Payments can only be recorded on sent invoices."})
    amount = int(data["amount"])
    owed_before = invoice.balance
    balance = format_money(owed_before, invoice.currency)
    if amount > owed_before and not online:
        raise ValidationError({"amount": [f"That is more than the balance of {balance}."]})
    paid_on = data.setdefault("paid_on", timezone.localdate())
    payment = Payment.objects.create(
        business=invoice.business,
        invoice=invoice,
        recorded_by=user if getattr(user, "is_authenticated", False) else None,
        source=Payment.Source.ONLINE if online else Payment.Source.MANUAL,
        receipt_number=next_number(invoice.business, paid_on.year, prefix="RCT"),
        **data,
    )
    label = Payment.Method(payment.method).label
    money = format_money(amount, invoice.currency)
    log(
        invoice.business,
        ActivityLog.Verb.PAID_ONLINE if online else ActivityLog.Verb.PAYMENT_RECORDED,
        f"Paid {money} online ({label})" if online else f"Payment {money} recorded ({label})",
        invoice=invoice,
        actor=user,
        payment_id=payment.pk,
    )
    if amount > owed_before:
        over = format_money(amount - owed_before, invoice.currency)
        log(
            invoice.business,
            ActivityLog.Verb.PAYMENT_RECORDED,
            f"Overpaid by {over}. Refund the customer or keep it as credit.",
            invoice=invoice,
        )
    return payment


@transaction.atomic
def delete_payment(payment: Any, user: Any) -> None:
    if payment.source == "online":
        raise ValidationError(
            {"detail": "Online payments came through Lenco and can't be deleted. Refund in Lenco."}
        )
    invoice = _lock(payment.invoice)
    amount = format_money(payment.amount, invoice.currency)
    payment.delete()
    log(
        invoice.business,
        ActivityLog.Verb.PAYMENT_DELETED,
        f"Payment {amount} deleted",
        invoice=invoice,
        actor=user,
    )


def mark_viewed(invoice: Invoice) -> None:
    """First customer view only, so the timeline isn't spammed by refreshes."""
    updated = Invoice.objects.filter(pk=invoice.pk, viewed_at__isnull=True).update(
        viewed_at=timezone.now()
    )
    if updated:
        log(invoice.business, ActivityLog.Verb.VIEWED, "Viewed by customer", invoice=invoice)
