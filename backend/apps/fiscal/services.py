"""Reporting invoices to ZRA. Called from apps.invoices.services inside its transaction, so a
VSDC failure leaves the invoice as it was (still a draft, or still not void)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Business
from apps.audit.models import ActivityLog, log

from . import vsdc
from .models import FiscalReceipt, ZraDevice

if TYPE_CHECKING:
    from apps.invoices.models import Invoice


def active_device(business: Business) -> ZraDevice | None:
    """The business's VSDC if it fiscalises. Raises if it's switched on but not set up."""
    if not business.vat_registered:
        return None
    device = ZraDevice.objects.filter(business=business, enabled=True).first()
    if device is None:
        return None
    if not device.is_ready:
        raise ValidationError(
            {
                "detail": "ZRA Smart Invoice is on but not set up. Add your TPIN, device serial "
                "and item class code in Settings, or switch it off."
            }
        )
    return device


GENERAL = {"A": 1, "B": 2, "C1": 3, "C2": 4, "C3": 5, "D": 6}


def item_code(device: ZraDevice, line: Any, category: str) -> str:
    """ZRA's item code formula (spec 6.16): country, product type, packaging unit, quantity unit,
    then a 7-digit number. Catalog items use their id; one-off lines share a "general" code per
    VAT category, numbered from 9900001 so they never meet a catalog id."""
    prefix = f"{vsdc.ORIGIN_COUNTRY}{device.item_type}{vsdc.PKG_UNIT}{vsdc.QTY_UNIT}"
    number = line.item_id if line.item_id else 9_900_000 + GENERAL.get(category, 9)
    return f"{prefix}{number:07d}"


def fiscal_lines(invoice: Invoice, device: ZraDevice) -> list[vsdc.Line]:
    lines = []
    for line in invoice.lines.select_related("item").order_by("position", "id"):  # type: ignore[attr-defined]
        category = (
            line.vat_category
            or (line.item.vat_category if line.item else "")
            or device.default_vat_category
        )
        lines.append(
            vsdc.Line(
                code=item_code(device, line, category),
                name=line.description,
                item_name=line.item.name if line.item else f"General sale ({category})",
                category=category,
                quantity=line.quantity,
                unit_price=line.unit_price,
                discount=line.discount,
            )
        )
    return lines


def ensure_items(client: vsdc.Client, device: ZraDevice, lines: list[vsdc.Line]) -> None:
    """Save each item code on the VSDC once (and again if its VAT category changed)."""
    known: dict[str, str] = dict(device.registered_items or {})
    changed = False
    for line in lines:
        if known.get(line.code) == line.category:
            continue
        body = vsdc.item_payload(device, line)
        try:
            client.save_item(body, update=line.code in known)
        except vsdc.VsdcError:
            if line.code in known:
                raise
            client.save_item(body, update=True)  # saved before, e.g. by a send that failed later
        known[line.code] = line.category
        changed = True
    if changed:
        device.registered_items = known
        device.save(update_fields=["registered_items", "updated_at"])


def _report(
    invoice: Invoice,
    device: ZraDevice,
    *,
    kind: str,
    number: str,
    credit_for: FiscalReceipt | None = None,
    reason: str = "",
) -> FiscalReceipt:
    if invoice.currency != "ZMW" and not invoice.exchange_rate:
        raise ValidationError(
            {"exchange_rate": "ZRA needs the Kwacha exchange rate for this invoice."}
        )
    lines = fiscal_lines(invoice, device)
    customer = invoice.customer
    body = vsdc.sale_payload(
        device,
        number=number,
        lines=lines,
        customer_name=customer.name,
        customer_tpin=customer.tpin,
        currency=invoice.currency,
        exchange_rate=invoice.exchange_rate,
        sale_date=timezone.localdate() if credit_for else invoice.issue_date,
        total=invoice.total,
        credit_for=credit_for,
        reason=reason,
    )
    client = vsdc.Client(device)
    try:
        ensure_items(client, device, lines)
        try:
            answer = client.save_sale(body)
        except vsdc.VsdcError as exc:
            if exc.code != vsdc.DUPLICATE or not device.sdc_id:
                raise
            # ZRA already has this number: an earlier send got through but we lost the answer
            # (e.g. a timeout). Fetch the signed receipt instead of failing.
            answer = client.select_invoice(number)
    except vsdc.VsdcError as exc:
        raise ValidationError({"detail": f"ZRA didn't accept this invoice. {exc}"}) from exc
    if kind == FiscalReceipt.Kind.SALE:  # keep what was reported, so a credit note matches
        for line, sent in zip(invoice.lines.all(), lines, strict=True):  # type: ignore[attr-defined]
            if line.vat_category != sent.category:
                line.vat_category = sent.category
                line.save(update_fields=["vat_category"])
    fields = vsdc.receipt_fields(answer)
    receipt = FiscalReceipt.objects.create(
        business=invoice.business,
        invoice=invoice,
        kind=kind,
        document_number=number,
        taxable_total=body["totTaxblAmt"],
        tax_total=body["totTaxAmt"],
        vat_summary=vsdc.vat_summary(lines),
        request=body,
        response=answer,
        **{**fields, "sdc_id": fields["sdc_id"] or device.sdc_id},
    )
    what = "Tax invoice" if kind == FiscalReceipt.Kind.SALE else f"Credit note {number}"
    log(
        invoice.business,
        ActivityLog.Verb.UPDATED,
        f"{what} signed by ZRA (receipt {receipt.receipt_no or '?'})",
        invoice=invoice,
    )
    return receipt


def fiscalise(invoice: Invoice) -> FiscalReceipt | None:
    """Report a sale to ZRA if the business fiscalises. Idempotent."""
    device = active_device(invoice.business)
    if device is None:
        return None
    existing = invoice.fiscal_receipts.filter(kind=FiscalReceipt.Kind.SALE).first()  # type: ignore[attr-defined]
    if existing:
        return existing  # type: ignore[no-any-return]
    return _report(invoice, device, kind=FiscalReceipt.Kind.SALE, number=invoice.number)


def credit_note(invoice: Invoice, reason: str = "") -> FiscalReceipt | None:
    """Cancel a fiscalised invoice with a credit note for its full amount."""
    from apps.invoices.services import next_number

    sale = invoice.fiscal_receipts.filter(kind=FiscalReceipt.Kind.SALE).first()  # type: ignore[attr-defined]
    if sale is None:
        return None
    existing = invoice.fiscal_receipts.filter(kind=FiscalReceipt.Kind.CREDIT).first()  # type: ignore[attr-defined]
    if existing:
        return existing  # type: ignore[no-any-return]
    device = ZraDevice.objects.filter(business=invoice.business).first()
    if device is None or not device.is_ready:
        raise ValidationError(
            {
                "detail": "This is a ZRA tax invoice, so voiding it needs a credit note. "
                "Turn ZRA Smart Invoice back on in Settings first."
            }
        )
    number = next_number(invoice.business, timezone.localdate().year, prefix="CN")
    return _report(
        invoice,
        device,
        kind=FiscalReceipt.Kind.CREDIT,
        number=number,
        credit_for=sale,
        reason=reason,
    )
