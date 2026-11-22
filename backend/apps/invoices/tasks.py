from celery import shared_task

from .models import Invoice
from .pdf import get_or_build_pdf


@shared_task(ignore_result=True)
def build_invoice_pdf(invoice_id: int) -> None:
    """Pre-render the PDF after sending so the customer's first download is instant."""
    invoice = Invoice.objects.filter(pk=invoice_id).select_related("business", "customer").first()
    if invoice is not None:
        get_or_build_pdf(invoice)
