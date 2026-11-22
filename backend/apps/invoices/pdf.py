import hashlib

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.template.loader import render_to_string

from .models import Invoice

TEMPLATE_VERSION = "1"


def document_context(invoice: Invoice) -> dict[str, object]:
    return {
        "invoice": invoice,
        "business": invoice.business,
        "customer": invoice.customer,
        "lines": list(invoice.lines.all()),  # type: ignore[attr-defined]
        "payments": list(invoice.payments.all()),  # type: ignore[attr-defined]
    }


def pdf_fingerprint(invoice: Invoice) -> str:
    """Changes whenever anything printed on the PDF changes, so cached PDFs are never stale."""
    b = invoice.business
    parts = [
        TEMPLATE_VERSION,
        invoice.updated_at.isoformat(),
        str(invoice.amount_paid),
        invoice.display_status,
        b.updated_at.isoformat(),
        invoice.customer.updated_at.isoformat(),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def pdf_path(invoice: Invoice) -> str:
    return f"invoices/{invoice.business_id}/{invoice.public_token}-{pdf_fingerprint(invoice)}.pdf"


def render_pdf(invoice: Invoice) -> bytes:
    from weasyprint import HTML  # heavy import; only where needed

    html = render_to_string("invoices/document.html", {**document_context(invoice), "pdf": True})
    return HTML(string=html).write_pdf()  # type: ignore[no-any-return]


def get_or_build_pdf(invoice: Invoice) -> bytes:
    path = pdf_path(invoice)
    if default_storage.exists(path):
        with default_storage.open(path, "rb") as fh:
            return fh.read()  # type: ignore[no-any-return]
    data = render_pdf(invoice)
    default_storage.save(path, ContentFile(data))
    return data


def pdf_filename(invoice: Invoice) -> str:
    return f"{invoice.number}.pdf"
