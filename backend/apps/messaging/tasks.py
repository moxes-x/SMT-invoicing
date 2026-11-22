import logging
from typing import Any

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from apps.audit.models import ActivityLog, log
from apps.invoices.pdf import get_or_build_pdf, pdf_filename

from . import whatsapp
from .models import Delivery
from .services import content_for

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


class PermanentFailure(Exception):
    pass


def _send_email(delivery: Delivery, doc: Any, message: str) -> str:
    content = content_for(doc, delivery.kind)
    business = doc.business
    context = {
        "doc": doc,
        "business": business,
        "message": message or content.text.split("\n\n")[0],
        **content.__dict__,
    }
    subjects: dict[str, str] = {
        "reminder": f"Reminder: invoice {doc.number} from {business.name}",
        "quote": f"Quote {doc.number} from {business.name}",
    }
    subject = subjects.get(delivery.kind, f"Invoice {doc.number} from {business.name}")
    email = EmailMultiAlternatives(
        subject=subject,
        body=render_to_string("emails/document.txt", context),
        from_email=f"{business.name} <{settings.DEFAULT_FROM_EMAIL}>".replace('"', ""),
        to=[delivery.recipient],
        reply_to=[business.email] if business.email else None,
    )
    email.attach_alternative(render_to_string("emails/document.html", context), "text/html")
    email.attach(pdf_filename(doc), get_or_build_pdf(doc), "application/pdf")
    email.send()
    status = getattr(email, "anymail_status", None)  # set when an anymail backend is used
    return (getattr(status, "message_id", None) or "")[:200]


def _send_whatsapp(delivery: Delivery, doc: Any) -> str:
    if not whatsapp.is_enabled():
        raise PermanentFailure("WhatsApp Cloud API is not configured.")
    content = content_for(doc, delivery.kind)
    try:
        return whatsapp.Client().send_template(
            delivery.recipient,
            settings.WHATSAPP_TEMPLATES[delivery.kind],
            content.params,
            whatsapp.Document(pdf_filename(doc), get_or_build_pdf(doc)),
        )
    except whatsapp.WhatsAppError as exc:
        if not exc.retryable:
            raise PermanentFailure(str(exc)) from exc
        raise


@shared_task(bind=True, ignore_result=True, max_retries=MAX_ATTEMPTS - 1, default_retry_delay=60)
def send_delivery(self: Any, delivery_id: int, message: str = "") -> None:
    delivery = Delivery.objects.select_related(
        "business", "invoice__customer", "quote__customer"
    ).get(pk=delivery_id)
    if delivery.status != Delivery.Status.QUEUED:
        return  # already handled (task redelivered)
    doc: Any = delivery.invoice or delivery.quote
    delivery.attempts += 1
    try:
        if delivery.channel == Delivery.Channel.EMAIL:
            provider_id = _send_email(delivery, doc, message)
        else:
            provider_id = _send_whatsapp(delivery, doc)
    except Exception as exc:
        delivery.error = str(exc)[:2000]
        if not isinstance(exc, PermanentFailure) and delivery.attempts < MAX_ATTEMPTS:
            delivery.save(update_fields=["attempts", "error", "updated_at"])
            raise self.retry(exc=exc) from exc
        delivery.status = Delivery.Status.FAILED
        delivery.save(update_fields=["attempts", "error", "status", "updated_at"])
        _log(delivery, doc, ActivityLog.Verb.DELIVERY_FAILED, "failed")
        return

    delivery.provider_message_id = provider_id
    delivery.status = Delivery.Status.SENT
    delivery.error = ""
    delivery.save()
    verb = {
        Delivery.Channel.EMAIL: ActivityLog.Verb.EMAILED,
        Delivery.Channel.WHATSAPP: ActivityLog.Verb.SENT,
    }[Delivery.Channel(delivery.channel)]
    if delivery.kind == Delivery.Kind.REMINDER:
        verb = ActivityLog.Verb.REMINDED
    _log(delivery, doc, verb, "sent")


def _log(delivery: Delivery, doc: Any, verb: str, what: str) -> None:
    label = {"reminder": "Reminder", "quote": "Quote", "invoice": "Invoice"}[delivery.kind]
    via = "email" if delivery.channel == Delivery.Channel.EMAIL else "WhatsApp"
    auto = " (automatic)" if delivery.automatic else ""
    message = f"{label} {what} by {via} to {delivery.recipient}{auto}"
    log(
        delivery.business,
        verb,
        message[:300],
        invoice=delivery.invoice,
        quote=delivery.quote,
    )


@shared_task(ignore_result=True)
def send_overdue_reminders() -> int:
    from .reminders import send_due_reminders

    count = send_due_reminders()
    logger.info("Queued %s overdue reminders", count)
    return count
