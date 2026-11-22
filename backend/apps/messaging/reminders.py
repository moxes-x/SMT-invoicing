"""Automatic overdue reminders, run daily by Celery beat."""

from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone

from apps.core.time import today as lusaka_today
from apps.invoices.models import Invoice

from .models import Delivery
from .services import send_automatically


def reminders_sent(invoice: Invoice):  # type: ignore[no-untyped-def]
    return Delivery.objects.filter(invoice=invoice, kind=Delivery.Kind.REMINDER).exclude(
        status=Delivery.Status.FAILED
    )


def is_due(invoice: Invoice, today: dt.date) -> bool:
    """Overdue, not paused, under the business's cap, and quiet for at least the interval."""
    business = invoice.business
    if not business.auto_reminders or invoice.reminders_paused:
        return False
    if not invoice.is_overdue(today):
        return False
    previous = reminders_sent(invoice)
    if previous.count() >= business.max_reminders:
        return False
    last = previous.order_by("-created_at").first()
    if last is not None:
        days = (today - timezone.localdate(last.created_at)).days
        if days < business.reminder_interval_days:
            return False
    return True


def send_due_reminders(today: dt.date | None = None) -> int:
    today = today or lusaka_today()
    candidates = (
        Invoice.objects.overdue(today)  # type: ignore[attr-defined]
        .filter(business__auto_reminders=True, reminders_paused=False)
        .values_list("pk", flat=True)
    )
    queued = 0
    for pk in list(candidates):
        with transaction.atomic():
            # skip_locked: if two workers run the job at once, each invoice is handled once.
            invoice = (
                Invoice.objects.select_for_update(skip_locked=True, of=("self",))
                .select_related("business", "customer")
                .filter(pk=pk)
                .first()
            )
            if invoice is None:
                continue
            invoice = (
                Invoice.objects.with_balance()
                .select_related(  # type: ignore[attr-defined]
                    "business", "customer"
                )
                .get(pk=pk)
            )
            if is_due(invoice, today) and send_automatically(invoice, kind=Delivery.Kind.REMINDER):
                queued += 1
    return queued
