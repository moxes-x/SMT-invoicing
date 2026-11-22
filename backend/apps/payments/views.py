import csv
import datetime as dt
from typing import Any

from django.db.models import QuerySet
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.tenancy import BusinessScopedMixin, HasBusiness, require_business, require_manager
from apps.invoices.services import delete_payment

from . import lenco
from .models import LencoAccount, Payment
from .serializers import ConnectionTestSerializer, LencoAccountSerializer, PaymentSerializer

DATE_RANGE = [
    OpenApiParameter("start", OpenApiTypes.DATE, description="From this date (inclusive)"),
    OpenApiParameter("end", OpenApiTypes.DATE, description="Up to this date (inclusive)"),
]


def parse_range(request: Request) -> tuple[dt.date | None, dt.date | None]:
    out: list[dt.date | None] = []
    for key in ("start", "end"):
        raw = request.query_params.get(key)
        try:
            out.append(dt.date.fromisoformat(raw) if raw else None)
        except ValueError as exc:
            raise ValidationError({key: "Use a date like 2026-11-30."}) from exc
    return out[0], out[1]


def major(ngwee: int) -> str:
    sign = "-" if ngwee < 0 else ""
    return f"{sign}{abs(ngwee) // 100}.{abs(ngwee) % 100:02d}"


def csv_response(filename: str, header: list[str], rows: Any) -> HttpResponse:
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")  # so Excel opens UTF-8 correctly
    writer = csv.writer(response)
    writer.writerow(header)
    writer.writerows(rows)
    return response


class PaymentViewSet(
    BusinessScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet[Payment],
):
    """Payments are recorded via POST /invoices/{id}/payments/; listed and undone here."""

    queryset = Payment.objects.select_related("invoice")
    serializer_class = PaymentSerializer
    permission_classes = [HasBusiness]
    manager_actions = ("destroy",)
    lookup_value_regex = r"\d+"

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        delete_payment(self.get_object(), request.user)
        return Response(status=204)

    @extend_schema(parameters=DATE_RANGE, responses={(200, "text/csv"): OpenApiTypes.STR})
    @action(detail=False, methods=["get"])
    def export(self, request: Request) -> HttpResponse:
        """All payments as CSV (amounts in Kwacha, e.g. 1250.00), for accounting or ZRA records."""
        start, end = parse_range(request)
        qs: QuerySet[Payment] = self.get_queryset().select_related("invoice__customer")
        if start:
            qs = qs.filter(paid_on__gte=start)
        if end:
            qs = qs.filter(paid_on__lte=end)
        rows = (
            [
                p.paid_on.isoformat(),
                p.receipt_number,
                p.invoice.number,
                p.invoice.customer.name,
                p.invoice.currency,
                major(p.amount),
                p.get_method_display(),
                p.get_source_display(),
                p.reference,
                p.note,
            ]
            for p in qs.order_by("paid_on", "id")
        )
        return csv_response(
            "payments.csv",
            [
                "Date",
                "Receipt",
                "Invoice",
                "Customer",
                "Currency",
                "Amount",
                "Method",
                "Source",
                "Reference",
                "Note",
            ],
            rows,
        )


def _account(request: Request) -> LencoAccount:
    account, _ = LencoAccount.objects.get_or_create(business=require_business(request))
    return account


def _require_admin(request: Request) -> None:
    require_manager(request)


@extend_schema(methods=["GET"], responses=LencoAccountSerializer)
@extend_schema(methods=["PUT"], request=LencoAccountSerializer, responses=LencoAccountSerializer)
@api_view(["GET", "PUT"])
@permission_classes([HasBusiness])
def online_payments(request: Request) -> Response:
    """The current business's Lenco account. The secret key is write-only and stored encrypted."""
    account = _account(request)
    if request.method == "PUT":
        _require_admin(request)
        ser = LencoAccountSerializer(account, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)
    return Response(LencoAccountSerializer(account).data)


@extend_schema(request=None, responses=ConnectionTestSerializer)
@api_view(["POST"])
@permission_classes([HasBusiness])
def test_online_payments(request: Request) -> Response:
    """Check the saved keys against Lenco by looking up a reference that can't exist."""
    _require_admin(request)
    account = _account(request)
    if not account.secret_key:
        return Response({"ok": False, "message": "Save your secret key first."})
    try:
        lenco.Client(account).collection_status("connection-test")
    except lenco.LencoError as exc:
        if exc.status_code == 404:
            return Response({"ok": True, "message": "Connected to Lenco."})
        if exc.status_code in (401, 403):
            return Response({"ok": False, "message": "Lenco didn't accept this secret key."})
        return Response({"ok": False, "message": str(exc)})
    return Response({"ok": True, "message": "Connected to Lenco."})
