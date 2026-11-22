from typing import Any

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from apps.audit.models import ActivityLog, log
from apps.invoices.pdf import get_or_build_pdf, pdf_filename

from .models import Delivery
from .services import invoice_message

MAX_ATTEMPTS = 3


@shared_task(bind=True, ignore_result=True, max_retries=MAX_ATTEMPTS - 1, default_retry_delay=60)
def send_invoice_email(self: Any, delivery_id: int, message: str = "") -> None:
    delivery = Delivery.objects.select_related(
        "invoice", "invoice__business", "invoice__customer"
    ).get(pk=delivery_id)
    if delivery.status != Delivery.Status.QUEUED:
        return  # already handled (task redelivered)
    invoice = delivery.invoice
    business = invoice.business
    delivery.attempts += 1
    try:
        context = {
            "invoice": invoice,
            "business": business,
            "message": message or invoice_message(invoice).split("\n\n")[0],
        }
        email = EmailMultiAlternatives(
            subject=f"Invoice {invoice.number} from {business.name}",
            body=render_to_string("emails/invoice.txt", context),
            from_email=f"{business.name} <{settings.DEFAULT_FROM_EMAIL}>".replace('"', ""),
            to=[delivery.recipient],
            reply_to=[business.email] if business.email else None,
        )
        email.attach_alternative(render_to_string("emails/invoice.html", context), "text/html")
        email.attach(pdf_filename(invoice), get_or_build_pdf(invoice), "application/pdf")
        email.send()
    except Exception as exc:
        delivery.error = str(exc)[:2000]
        if delivery.attempts < MAX_ATTEMPTS:
            delivery.save(update_fields=["attempts", "error", "updated_at"])
            raise self.retry(exc=exc) from exc
        delivery.status = Delivery.Status.FAILED
        delivery.save(update_fields=["attempts", "error", "status", "updated_at"])
        log(
            business,
            ActivityLog.Verb.EMAIL_FAILED,
            f"Email to {delivery.recipient} failed",
            invoice=invoice,
        )
        return

    status = getattr(email, "anymail_status", None)  # set when an anymail backend is used
    delivery.provider_message_id = (getattr(status, "message_id", None) or "")[:200]
    delivery.status = Delivery.Status.SENT
    delivery.error = ""
    delivery.save()
    log(business, ActivityLog.Verb.EMAILED, f"Emailed to {delivery.recipient}", invoice=invoice)
