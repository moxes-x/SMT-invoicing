"""Business reports: invoiced, collected and owed, per currency, plus a Kwacha view.

Amounts in different currencies are never added together. The Kwacha view converts each
foreign-currency invoice (and its payments and balance) at the invoice's own exchange rate,
and counts the invoices that have no rate yet instead of guessing one.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from django.db.models import Count, F, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import Business
from apps.core.money import to_kwacha
from apps.core.tenancy import HasBusiness, require_business
from apps.payments.models import Payment
from apps.payments.views import DATE_RANGE, csv_response, major, parse_range

from .models import Invoice

AGING = [
    ("not_due", "Not due yet", None, 0),
    ("1_30", "1–30 days late", 1, 30),
    ("31_60", "31–60 days late", 31, 60),
    ("61_90", "61–90 days late", 61, 90),
    ("over_90", "Over 90 days late", 91, None),
]
MAX_DAYS = 366 * 3


# ---- serializers (for the schema) -----------------------------------------------------------
class AmountSerializer(serializers.Serializer[Any]):
    amount = serializers.IntegerField()
    count = serializers.IntegerField()


class MethodSerializer(AmountSerializer):
    method = serializers.CharField()
    name = serializers.CharField()


class AgingSerializer(AmountSerializer):
    bucket = serializers.CharField()
    name = serializers.CharField()


class MonthSerializer(serializers.Serializer[Any]):
    month = serializers.CharField(help_text="YYYY-MM")
    invoiced = serializers.IntegerField()
    collected = serializers.IntegerField()


class TopCustomerSerializer(serializers.Serializer[Any]):
    customer_id = serializers.IntegerField()
    name = serializers.CharField()
    invoiced = serializers.IntegerField()
    count = serializers.IntegerField()


class CurrencyReportSerializer(serializers.Serializer[Any]):
    currency = serializers.CharField()
    invoiced = AmountSerializer()
    collected = AmountSerializer()
    outstanding = AmountSerializer()
    overdue = AmountSerializer()
    by_method = MethodSerializer(many=True)
    aging = AgingSerializer(many=True)
    months = MonthSerializer(many=True)
    top_customers = TopCustomerSerializer(many=True)


class KwachaSerializer(serializers.Serializer[Any]):
    invoiced = serializers.IntegerField()
    collected = serializers.IntegerField()
    outstanding = serializers.IntegerField()
    overdue = serializers.IntegerField()
    months = MonthSerializer(many=True)
    missing_rates = serializers.IntegerField(
        help_text="Foreign-currency invoices left out because they have no exchange rate"
    )


class ReportSerializer(serializers.Serializer[Any]):
    start = serializers.DateField()
    end = serializers.DateField()
    as_of = serializers.DateField(help_text="Outstanding and overdue are as of this day")
    currencies = CurrencyReportSerializer(many=True)
    kwacha = KwachaSerializer(help_text="Everything in Kwacha at each invoice's own rate")


# ---- building ------------------------------------------------------------------------------
def report_range(request: Request) -> tuple[dt.date, dt.date]:
    start, end = parse_range(request)
    today = timezone.localdate()
    end = end or today
    start = start or end.replace(day=1)
    if start > end:
        raise ValidationError({"start": "Start must be on or before end."})
    if (end - start).days > MAX_DAYS:
        raise ValidationError({"start": "Pick at most three years at a time."})
    return start, end


def month_keys(start: dt.date, end: dt.date) -> list[str]:
    keys, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        keys.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return keys


def _bucket(days_late: int) -> str:
    for key, _, lo, hi in AGING:
        if (lo is None and days_late <= 0) or (
            lo is not None and days_late >= lo and (hi is None or days_late <= hi)
        ):
            return key
    return AGING[-1][0]


def _blank(currency: str, months: list[str]) -> dict[str, Any]:
    zero = {"amount": 0, "count": 0}
    return {
        "currency": currency,
        "invoiced": dict(zero),
        "collected": dict(zero),
        "outstanding": dict(zero),
        "overdue": dict(zero),
        "by_method": [],
        "aging": [{"bucket": k, "name": name, **zero} for k, name, _, _ in AGING],
        "months": [{"month": m, "invoiced": 0, "collected": 0} for m in months],
        "top_customers": [],
    }


def build_report(business: Business, start: dt.date, end: dt.date) -> dict[str, Any]:
    today = timezone.localdate()
    months = month_keys(start, end)
    by_cur: dict[str, dict[str, Any]] = {}

    def cur(c: str) -> dict[str, Any]:
        if c not in by_cur:
            by_cur[c] = _blank(c, months)
        return by_cur[c]

    kw: dict[str, Any] = {"invoiced": 0, "collected": 0, "outstanding": 0, "overdue": 0}
    kw_months: dict[str, dict[str, Any]] = {
        m: {"month": m, "invoiced": 0, "collected": 0} for m in months
    }
    missing: set[int] = set()

    def add_kwacha(
        key: str,
        amount: int,
        currency: str,
        rate: Decimal | None,
        inv_id: int,
        month: str | None = None,
    ) -> None:
        value = to_kwacha(amount, currency, rate)
        if value is None:
            missing.add(inv_id)
            return
        kw[key] += value
        if month is not None:
            kw_months[month][key] += value

    # Invoiced: sent (not draft, not void) and issued in the range. A reissued invoice's void
    # original drops out and its replacement counts.
    issued = Invoice.objects.filter(
        business=business, status=Invoice.Status.SENT, issue_date__range=(start, end)
    )
    for r1 in issued.values("currency").annotate(amount=Sum("total"), count=Count("id")):
        cur(r1["currency"])["invoiced"] = {"amount": r1["amount"] or 0, "count": r1["count"]}
    for r2 in (
        issued.annotate(m=TruncMonth("issue_date"))
        .values("currency", "m")
        .annotate(amount=Sum("total"))
    ):
        key = r2["m"].strftime("%Y-%m")
        for row in cur(r2["currency"])["months"]:
            if row["month"] == key:
                row["invoiced"] = r2["amount"] or 0
    for inv_id, currency, rate, total, issue_date in issued.values_list(
        "id", "currency", "exchange_rate", "total", "issue_date"
    ):
        add_kwacha("invoiced", total, currency, rate, inv_id, issue_date.strftime("%Y-%m"))

    top = (
        issued.values("customer_id", "customer__name", "currency")
        .annotate(invoiced=Sum("total"), count=Count("id"))
        .order_by("-invoiced")
    )
    for r3 in top:
        rows = cur(r3["currency"])["top_customers"]
        if len(rows) < 5:
            rows.append(
                {
                    "customer_id": r3["customer_id"],
                    "name": r3["customer__name"],
                    "invoiced": r3["invoiced"] or 0,
                    "count": r3["count"],
                }
            )

    # Collected: payments received in the range, whenever the invoice was issued.
    paid = Payment.objects.filter(business=business, paid_on__range=(start, end))
    labels = dict(Payment.Method.choices)
    for r4 in (
        paid.values(currency=F("invoice__currency"))
        .annotate(amount=Sum("amount"), count=Count("id"))
        .order_by()
    ):
        cur(r4["currency"])["collected"] = {"amount": r4["amount"] or 0, "count": r4["count"]}
    for r5 in (
        paid.values("method", currency=F("invoice__currency"))
        .annotate(amount=Sum("amount"), count=Count("id"))
        .order_by("-amount")
    ):
        cur(r5["currency"])["by_method"].append(
            {
                "method": r5["method"],
                "name": labels.get(r5["method"], r5["method"]),
                "amount": r5["amount"] or 0,
                "count": r5["count"],
            }
        )
    for r6 in (
        paid.annotate(m=TruncMonth("paid_on"))
        .values("m", currency=F("invoice__currency"))
        .annotate(amount=Sum("amount"))
        .order_by()
    ):
        key = r6["m"].strftime("%Y-%m")
        for row in cur(r6["currency"])["months"]:
            if row["month"] == key:
                row["collected"] = r6["amount"] or 0
    for inv_id, currency, rate, amount, paid_on in paid.values_list(
        "invoice_id", "invoice__currency", "invoice__exchange_rate", "amount", "paid_on"
    ):
        add_kwacha("collected", amount, currency, rate, inv_id, paid_on.strftime("%Y-%m"))

    # Owed: right now, whenever issued.
    outstanding: Any = Invoice.objects.filter(business=business).outstanding()  # type: ignore[attr-defined]
    for inv_id, currency, rate, balance, due in outstanding.values_list(
        "id", "currency", "exchange_rate", "balance_amount", "due_date"
    ):
        c = cur(currency)
        c["outstanding"]["amount"] += balance
        c["outstanding"]["count"] += 1
        late = (today - due).days
        if late > 0:
            c["overdue"]["amount"] += balance
            c["overdue"]["count"] += 1
            add_kwacha("overdue", balance, currency, rate, inv_id)
        add_kwacha("outstanding", balance, currency, rate, inv_id)
        bucket = next(b for b in c["aging"] if b["bucket"] == _bucket(late))
        bucket["amount"] += balance
        bucket["count"] += 1

    currencies = sorted(by_cur.values(), key=lambda c: (c["currency"] != "ZMW", c["currency"]))
    if not currencies:
        currencies = [_blank(business.default_currency, months)]
    return {
        "start": start,
        "end": end,
        "as_of": today,
        "currencies": currencies,
        "kwacha": {**kw, "months": list(kw_months.values()), "missing_rates": len(missing)},
    }


# ---- views ---------------------------------------------------------------------------------
@extend_schema(parameters=DATE_RANGE, responses=ReportSerializer)
@api_view(["GET"])
@permission_classes([HasBusiness])
def report(request: Request) -> Response:
    """Invoiced and collected in a date range (default: this month), and owed right now."""
    start, end = report_range(request)
    return Response(ReportSerializer(build_report(require_business(request), start, end)).data)


@extend_schema(parameters=DATE_RANGE, responses={(200, "text/csv"): str})
@api_view(["GET"])
@permission_classes([HasBusiness])
def report_csv(request: Request) -> HttpResponse:
    """Month by month, per currency, with the Kwacha totals: for the accountant's spreadsheet."""
    start, end = report_range(request)
    data = build_report(require_business(request), start, end)
    rows: list[list[str]] = []
    for c in data["currencies"]:
        for m in c["months"]:
            rows.append([m["month"], c["currency"], major(m["invoiced"]), major(m["collected"])])
    for m in data["kwacha"]["months"]:
        rows.append([m["month"], "ZMW equivalent", major(m["invoiced"]), major(m["collected"])])
    return csv_response(
        f"report-{start}-to-{end}.csv", ["Month", "Currency", "Invoiced", "Collected"], rows
    )
