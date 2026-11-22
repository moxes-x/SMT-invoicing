"""PDF rendering for invoices and quotes (anything with business, customer, number, token)."""

import hashlib
from typing import Any

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.template.loader import render_to_string

TEMPLATE_VERSION = "2"


def document_context(doc: Any) -> dict[str, object]:
    ctx: dict[str, object] = {
        "doc": doc,
        "business": doc.business,
        "customer": doc.customer,
        "lines": list(doc.lines.all()),
    }
    if hasattr(doc, "payments"):
        ctx["invoice"] = doc
        ctx["payments"] = list(doc.payments.all())
    else:
        ctx["quote"] = doc
    return ctx


def pdf_fingerprint(doc: Any) -> str:
    """Changes whenever anything printed on the PDF changes, so cached PDFs are never stale."""
    parts = [
        TEMPLATE_VERSION,
        type(doc).__name__,
        doc.updated_at.isoformat(),
        doc.pdf_state(),
        doc.business.updated_at.isoformat(),
        doc.customer.updated_at.isoformat(),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def pdf_path(doc: Any) -> str:
    folder = type(doc).__name__.lower() + "s"
    return f"{folder}/{doc.business_id}/{doc.public_token}-{pdf_fingerprint(doc)}.pdf"


def render_pdf(doc: Any) -> bytes:
    from weasyprint import HTML  # heavy import; only where needed

    html = render_to_string(doc.DOCUMENT_TEMPLATE, {**document_context(doc), "pdf": True})
    return HTML(string=html).write_pdf()  # type: ignore[no-any-return]


def get_or_build_pdf(doc: Any) -> bytes:
    path = pdf_path(doc)
    if default_storage.exists(path):
        with default_storage.open(path, "rb") as fh:
            return fh.read()  # type: ignore[no-any-return]
    data = render_pdf(doc)
    default_storage.save(path, ContentFile(data))
    return data


def pdf_filename(doc: Any) -> str:
    return f"{doc.number}.pdf"
