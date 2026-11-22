"""Customer statements: what was invoiced and paid over a period, with a running balance."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from django.db.models import Sum

from apps.customers.models import Customer
from apps.payments.models import Payment

from .models import Invoice


@dataclass
class Row:
    date: dt.date
    kind: str  # "invoice" | "payment"
    reference: str
    description: str
    debit: int
    credit: int
    balance: int = 0
    invoice_id: int | None = None


@dataclass
class Statement:
    customer: Customer
    currency: str
    start: dt.date
    end: dt.date
    opening: int
    rows: list[Row] = field(default_factory=list)

    @property
    def invoiced(self) -> int:
        return sum(r.debit for r in self.rows)

    @property
    def paid(self) -> int:
        return sum(r.credit for r in self.rows)

    @property
    def closing(self) -> int:
        return self.opening + self.invoiced - self.paid


def _invoices(customer: Customer, currency: str) -> Any:
    # Drafts were never issued and void invoices were cancelled, so neither is owed.
    return Invoice.objects.filter(customer=customer, currency=currency, status=Invoice.Status.SENT)


def _payments(customer: Customer, currency: str) -> Any:
    return Payment.objects.filter(
        invoice__customer=customer, invoice__currency=currency, invoice__status=Invoice.Status.SENT
    )


def build_statement(customer: Customer, currency: str, start: dt.date, end: dt.date) -> Statement:
    invoices = _invoices(customer, currency)
    payments = _payments(customer, currency)
    opening = int(invoices.filter(issue_date__lt=start).aggregate(s=Sum("total"))["s"] or 0) - int(
        payments.filter(paid_on__lt=start).aggregate(s=Sum("amount"))["s"] or 0
    )
    rows = [
        Row(i.issue_date, "invoice", i.number, f"Invoice {i.number}", i.total, 0, invoice_id=i.pk)
        for i in invoices.filter(issue_date__range=(start, end))
    ] + [
        Row(
            p.paid_on,
            "payment",
            p.receipt_number or p.reference,
            f"Payment for {p.invoice.number} ({p.get_method_display()})",
            0,
            p.amount,
            invoice_id=p.invoice_id,
        )
        for p in payments.filter(paid_on__range=(start, end)).select_related("invoice")
    ]
    # Same day: invoice before the payment against it.
    rows.sort(key=lambda r: (r.date, r.kind != "invoice", r.reference))
    running = opening
    for r in rows:
        running += r.debit - r.credit
        r.balance = running
    return Statement(customer, currency, start, end, opening, rows)


def outstanding_invoices(customer: Customer, currency: str) -> list[Invoice]:
    return list(
        _invoices(customer, currency)
        .with_balance()  # type: ignore[attr-defined]
        .filter(balance_amount__gt=0)
        .order_by("due_date")
    )
