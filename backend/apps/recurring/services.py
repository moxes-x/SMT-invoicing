"""Turns recurring schedules into invoices. Run daily by Celery beat; safe to run twice."""

from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.models import ActivityLog, log
from apps.catalog.models import Item
from apps.core.time import today as lusaka_today
from apps.invoices.models import Invoice
from apps.invoices.services import LineData, create_invoice

from .models import RecurringInvoice

logger = logging.getLogger(__name__)
MAX_CATCH_UP = 12  # if the job was down for months, don't flood the customer


def lines_for_invoice(schedule: RecurringInvoice) -> list[LineData]:
    item_ids = {line.get("item") for line in schedule.lines if line.get("item")}
    items = {i.pk: i for i in Item.objects.filter(business=schedule.business, pk__in=item_ids)}
    return [
        {
            "item": items.get(line.get("item")),
            "description": line["description"],
            "quantity": Decimal(str(line["quantity"])),
            "unit_price": int(line["unit_price"]),
            "discount": int(line.get("discount") or 0),
        }
        for line in schedule.lines
    ]


def _advance(schedule: RecurringInvoice) -> None:
    schedule.runs += 1
    schedule.next_run_date = schedule.occurrence(schedule.runs)
    if schedule.is_finished:
        schedule.is_active = False


def generate_for(schedule_id: int, today: dt.date) -> list[Invoice]:
    """Create every invoice that's due for one schedule, then hand them to sending."""
    created: list[Invoice] = []
    with transaction.atomic():
        schedule = (
            RecurringInvoice.objects.select_for_update(skip_locked=True)
            .select_related("business", "customer")
            .filter(pk=schedule_id, is_active=True)
            .first()
        )
        if schedule is None:
            return created
        while (
            schedule.is_active
            and schedule.next_run_date <= today
            and not schedule.is_finished
            and len(created) < MAX_CATCH_UP
        ):
            issue = schedule.next_run_date
            try:
                with transaction.atomic():
                    invoice = create_invoice(
                        schedule.business,
                        None,
                        lines=lines_for_invoice(schedule),
                        customer=schedule.customer,
                        currency=schedule.currency,
                        issue_date=issue,
                        due_date=issue + dt.timedelta(days=schedule.days_until_due),
                        notes=schedule.notes,
                        recurring=schedule,
                    )
            except IntegrityError:
                # Already generated for this date (unique per schedule + issue date).
                logger.info("Schedule %s already has an invoice for %s", schedule.pk, issue)
            else:
                log(
                    schedule.business,
                    ActivityLog.Verb.GENERATED,
                    "Created automatically from a recurring schedule",
                    invoice=invoice,
                )
                created.append(invoice)
            _advance(schedule)
        if schedule.is_finished:
            schedule.is_active = False
        schedule.last_run_at = timezone.now()
        schedule.save()

        mode = schedule.send_mode
        if mode != RecurringInvoice.SendMode.DRAFT and created:
            from apps.messaging.models import Delivery
            from apps.messaging.services import send_automatically

            # Only the newest one goes out automatically; older catch-up invoices stay as
            # drafts so the owner can decide (avoids a burst of messages after downtime).
            latest = created[-1]
            sent = send_automatically(latest, kind=Delivery.Kind.INVOICE, channel=mode)
            if sent is None:
                log(
                    schedule.business,
                    ActivityLog.Verb.DELIVERY_FAILED,
                    f"Couldn't send automatically: customer has no "
                    f"{'WhatsApp number' if mode == 'whatsapp' else 'email address'}"
                    + (" or WhatsApp isn't set up" if mode == "whatsapp" else ""),
                    invoice=latest,
                )
    return created


def generate_recurring(today: dt.date | None = None) -> int:
    today = today or lusaka_today()
    due = RecurringInvoice.objects.filter(is_active=True, next_run_date__lte=today).values_list(
        "pk", flat=True
    )
    return sum(len(generate_for(pk, today)) for pk in list(due))


def preview_dates(schedule: Any, count: int = 3) -> list[dt.date]:
    dates: list[dt.date] = []
    n = schedule.runs
    while len(dates) < count:
        d = schedule.occurrence(n)
        if schedule.end_date and d > schedule.end_date:
            break
        dates.append(d)
        n += 1
    return dates
