"""Receipts: one per payment, as a public page and a cached PDF."""

from __future__ import annotations

import hashlib
from typing import Any

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.template.loader import render_to_string

from apps.invoices.models import Invoice

from .models import Payment

TEMPLATE_VERSION = "1"


def receipt_context(payment: Payment, *, pdf: bool = False) -> dict[str, Any]:
    invoice = Invoice.objects.with_balance().get(pk=payment.invoice_id)  # type: ignore[attr-defined]
    return {
        "payment": payment,
        "invoice": invoice,
        "business": payment.business,
        "customer": invoice.customer,
        "pdf": pdf,
    }


def _path(payment: Payment) -> str:
    # The balance shown on a receipt can change as later payments arrive.
    ctx = receipt_context(payment)
    parts = [
        TEMPLATE_VERSION,
        str(payment.amount),
        str(ctx["invoice"].balance),
        payment.business.updated_at.isoformat(),
    ]
    fp = hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
    return f"receipts/{payment.business_id}/{payment.public_token}-{fp}.pdf"


def get_or_build_receipt_pdf(payment: Payment) -> bytes:
    from weasyprint import HTML

    path = _path(payment)
    if default_storage.exists(path):
        with default_storage.open(path, "rb") as fh:
            return fh.read()  # type: ignore[no-any-return]
    html = render_to_string("payments/receipt.html", receipt_context(payment, pdf=True))
    data: bytes = HTML(string=html).write_pdf()
    default_storage.save(path, ContentFile(data))
    return data
