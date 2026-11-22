"""Customers paying invoices online through the business's own Lenco account."""

from __future__ import annotations

import datetime as dt
import logging
import secrets
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership
from apps.audit.models import ActivityLog, log
from apps.core.money import format_money
from apps.core.queue import enqueue_on_commit
from apps.invoices.models import Invoice

from . import lenco
from .models import LencoAccount, Payment, PaymentAttempt

logger = logging.getLogger(__name__)

# Don't hit Lenco more than this often for one attempt when a customer keeps refreshing.
CHECK_EVERY = dt.timedelta(seconds=4)
# How long the reconcile job keeps asking about an attempt nobody heard back about.
GIVE_UP_AFTER = dt.timedelta(hours=24)

STATUS_MAP = {
    "pending": PaymentAttempt.Status.PENDING,
    "pay-offline": PaymentAttempt.Status.PAY_OFFLINE,
    "3ds-auth-required": PaymentAttempt.Status.PENDING,
    "successful": PaymentAttempt.Status.SUCCESSFUL,
    "failed": PaymentAttempt.Status.FAILED,
}
METHOD_FOR_OPERATOR = {
    "mtn": Payment.Method.MTN_MOMO,
    "airtel": Payment.Method.AIRTEL_MONEY,
    "zamtel": Payment.Method.ZAMTEL_KWACHA,
}


def account_for(business: Any) -> LencoAccount | None:
    account = LencoAccount.objects.filter(business=business).first()
    return account if account and account.is_ready else None


def can_pay_online(invoice: Invoice) -> bool:
    """Lenco collects in Kwacha, so only ZMW invoices that are sent and unpaid get Pay now."""
    return (
        invoice.status == Invoice.Status.SENT
        and invoice.currency == "ZMW"
        and invoice.balance > 0
        and account_for(invoice.business) is not None
    )


def _new_reference(invoice: Invoice) -> str:
    # Lenco allows [-._a-zA-Z0-9]; unique per attempt so a retry never collides.
    return f"{invoice.number}-{secrets.token_hex(4)}"


def start_mobile_money(invoice: Invoice, *, phone: str, operator: str) -> PaymentAttempt:
    if not can_pay_online(invoice):
        raise ValidationError({"detail": "This invoice can't be paid online right now."})
    if operator not in PaymentAttempt.Operator.values:
        raise ValidationError({"operator": "Choose MTN, Airtel or Zamtel."})
    account = account_for(invoice.business)
    assert account is not None
    attempt = PaymentAttempt.objects.create(
        business=invoice.business,
        invoice=invoice,
        reference=_new_reference(invoice),
        channel=PaymentAttempt.Channel.MOBILE_MONEY,
        operator=operator,
        phone=phone,
        amount=invoice.balance,
        currency=invoice.currency,
    )
    try:
        data = lenco.Client(account).collect_mobile_money(
            reference=attempt.reference, amount=attempt.amount, phone=phone, operator=operator
        )
    except lenco.LencoError as exc:
        attempt.status = PaymentAttempt.Status.FAILED
        attempt.failure_reason = str(exc)[:300]
        attempt.save(update_fields=["status", "failure_reason", "updated_at"])
        return attempt
    return apply_collection(attempt, data)


def start_card(invoice: Invoice, *, email: str) -> PaymentAttempt:
    """The card itself is entered in Lenco's widget; we only reserve a reference to verify."""
    if not can_pay_online(invoice):
        raise ValidationError({"detail": "This invoice can't be paid online right now."})
    return PaymentAttempt.objects.create(
        business=invoice.business,
        invoice=invoice,
        reference=_new_reference(invoice),
        channel=PaymentAttempt.Channel.CARD,
        email=email,
        amount=invoice.balance,
        currency=invoice.currency,
    )


@transaction.atomic
def apply_collection(attempt: PaymentAttempt, data: dict[str, Any]) -> PaymentAttempt:
    """Apply Lenco's view of a collection. Safe to call any number of times, from any source."""
    attempt = (
        PaymentAttempt.objects.select_for_update().select_related("invoice").get(pk=attempt.pk)
    )
    status = STATUS_MAP.get(str(data.get("status")), attempt.status)
    if data.get("lencoReference"):
        attempt.lenco_reference = str(data["lencoReference"])[:100]
    attempt.last_checked_at = timezone.now()
    if attempt.status == PaymentAttempt.Status.SUCCESSFUL or attempt.payment_id:
        attempt.save(update_fields=["lenco_reference", "last_checked_at", "updated_at"])
        return attempt  # already turned into a payment; never twice

    attempt.status = status
    if status == PaymentAttempt.Status.FAILED:
        attempt.failure_reason = str(data.get("reasonForFailure") or "Payment failed")[:300]
    attempt.save()

    if status == PaymentAttempt.Status.SUCCESSFUL:
        _record(attempt, data)
    elif status == PaymentAttempt.Status.FAILED:
        log(
            attempt.business,
            ActivityLog.Verb.ONLINE_PAYMENT_FAILED,
            f"Online payment failed: {attempt.failure_reason}"[:300],
            invoice=attempt.invoice,
        )
    return attempt


def _record(attempt: PaymentAttempt, data: dict[str, Any]) -> None:
    from apps.invoices.services import record_payment

    # Record what Lenco says arrived, not what we asked for.
    amount = lenco.to_minor(data.get("amount")) or attempt.amount
    currency = str(data.get("currency") or attempt.currency)
    if currency != attempt.invoice.currency:
        logger.error("Lenco %s paid in %s for a %s invoice", attempt, currency, attempt.invoice)
    method = Payment.Method.CARD
    if attempt.channel == PaymentAttempt.Channel.MOBILE_MONEY or data.get("type") == "mobile-money":
        operator = (data.get("mobileMoneyDetails") or {}).get("operator") or attempt.operator
        method = METHOD_FOR_OPERATOR.get(str(operator), Payment.Method.OTHER)
    payment = record_payment(
        attempt.invoice,
        None,
        online=True,
        amount=amount,
        method=method,
        reference=(attempt.lenco_reference or attempt.reference)[:100],
        note="Paid online via Lenco",
    )
    attempt.payment = payment
    attempt.save(update_fields=["payment", "updated_at"])
    enqueue_on_commit(_notify_task(), payment.pk)


def _notify_task() -> Any:
    from .tasks import send_payment_notifications

    return send_payment_notifications


def refresh(attempt: PaymentAttempt, *, force: bool = False) -> PaymentAttempt:
    """Ask Lenco about an attempt that's still open (throttled unless forced)."""
    if not attempt.is_open:
        return attempt
    now = timezone.now()
    if not force and attempt.last_checked_at and now - attempt.last_checked_at < CHECK_EVERY:
        return attempt
    account = (
        account_for(attempt.business)
        or LencoAccount.objects.filter(business=attempt.business).first()
    )
    if account is None or not account.secret_key:
        return attempt
    try:
        data = lenco.Client(account).collection_status(attempt.reference)
    except lenco.LencoError as exc:
        # 404 for a card attempt just means the customer hasn't paid in the widget yet.
        if exc.status_code != 404:
            logger.warning("Lenco status check for %s failed: %s", attempt, exc)
        PaymentAttempt.objects.filter(pk=attempt.pk).update(last_checked_at=now)
        attempt.last_checked_at = now
        return attempt
    return apply_collection(attempt, data)


def reconcile_open_attempts(now: dt.datetime | None = None) -> int:
    """Re-check attempts still waiting (webhooks can be missed). Returns how many settled."""
    now = now or timezone.now()
    open_ = PaymentAttempt.objects.filter(
        status__in=[PaymentAttempt.Status.PENDING, PaymentAttempt.Status.PAY_OFFLINE],
        created_at__gte=now - GIVE_UP_AFTER,
        created_at__lte=now - dt.timedelta(minutes=1),
    )
    settled = 0
    for attempt in open_:
        if not refresh(attempt, force=True).is_open:
            settled += 1
    # Card attempts nobody completed: stop asking after a day.
    PaymentAttempt.objects.filter(
        status=PaymentAttempt.Status.PENDING, created_at__lt=now - GIVE_UP_AFTER
    ).update(status=PaymentAttempt.Status.FAILED, failure_reason="No payment received")
    return settled


def owner_emails(business: Any) -> list[str]:
    if business.email:
        return [business.email]
    return list(
        Membership.objects.filter(
            business=business, role__in=[Membership.Role.OWNER, Membership.Role.ADMIN]
        ).values_list("user__email", flat=True)
    )


def notify(payment: Payment) -> None:
    """Tell the owner the money arrived; send the customer their receipt if we have an email."""
    invoice = payment.invoice
    business = payment.business
    money = format_money(payment.amount, invoice.currency)
    context = {"payment": payment, "invoice": invoice, "business": business, "amount": money}
    to = owner_emails(business)
    if to:
        send_mail(
            f"Paid: {invoice.number} from {invoice.customer.name} ({money})",
            render_to_string("emails/payment_owner.txt", context),
            settings.DEFAULT_FROM_EMAIL,
            to,
        )
    if invoice.customer.email:
        send_mail(
            f"Receipt {payment.receipt_number} from {business.name}",
            render_to_string("emails/receipt.txt", context),
            f"{business.name} <{settings.DEFAULT_FROM_EMAIL}>".replace('"', ""),
            [invoice.customer.email],
        )
