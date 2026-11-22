import datetime as dt
from typing import Any

from django.db.models import Count, F, QuerySet, Sum
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.tenancy import BusinessScopedMixin, HasBusiness, require_business
from apps.messaging.services import queue_email, share_via_whatsapp
from apps.payments.models import Payment
from apps.payments.serializers import PaymentSerializer

from . import services
from .models import Invoice
from .pdf import get_or_build_pdf, pdf_filename
from .serializers import (
    DashboardSerializer,
    DeliverySerializer,
    EmailRequestSerializer,
    InvoiceListSerializer,
    InvoiceSerializer,
    ReasonSerializer,
    WhatsAppShareSerializer,
)

STATUS_FILTERS = ["draft", "sent", "void", "unpaid", "partial", "paid", "overdue"]


def filter_by_status(qs: Any, value: str) -> Any:
    today = timezone.localdate()
    sent = qs.filter(status=Invoice.Status.SENT)
    match value:
        case "draft" | "sent" | "void":
            return qs.filter(status=value)
        case "unpaid":  # anything still owed, including part-paid
            return sent.filter(balance_amount__gt=0)
        case "partial":
            return sent.filter(paid_amount__gt=0, balance_amount__gt=0)
        case "paid":
            return sent.filter(balance_amount__lte=0)
        case "overdue":
            return sent.filter(balance_amount__gt=0, due_date__lt=today)
    raise ValidationError({"status": f"Use one of: {', '.join(STATUS_FILTERS)}."})


@extend_schema(
    parameters=[
        OpenApiParameter("status", str, enum=STATUS_FILTERS),
        OpenApiParameter("customer", int),
    ]
)
class InvoiceViewSet(
    BusinessScopedMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet[Invoice],
):
    """Invoices are never deleted, only voided, so the numbering has no unexplained gaps."""

    queryset = Invoice.objects.all()
    permission_classes = [HasBusiness]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["number", "customer__name"]
    ordering_fields = ["issue_date", "due_date", "total", "number"]
    lookup_value_regex = r"\d+"

    def get_serializer_class(self) -> Any:
        return InvoiceListSerializer if self.action == "list" else InvoiceSerializer

    def get_queryset(self) -> QuerySet[Invoice]:
        qs = super().get_queryset().with_balance().select_related("customer", "business")  # type: ignore[attr-defined]
        if self.action != "list":
            qs = qs.select_related("reissued_from", "reissued_as").prefetch_related(
                "lines", "payments", "activity__actor"
            )
        params = self.request.query_params
        if value := params.get("status"):
            qs = filter_by_status(qs, value)
        if customer := params.get("customer"):
            qs = qs.filter(customer_id=customer) if customer.isdigit() else qs.none()
        return qs

    def perform_create(self, serializer: Any) -> None:
        serializer.save()  # business is stamped by services.create_invoice

    def _fresh(self, invoice: Invoice) -> Response:
        obj = self.get_queryset().get(pk=invoice.pk)
        return Response(InvoiceSerializer(obj, context=self.get_serializer_context()).data)

    @extend_schema(request=None, responses=InvoiceSerializer)
    @action(detail=True, methods=["post"])
    def send(self, request: Request, pk: str | None = None) -> Response:
        """Lock the invoice (draft → sent) without delivering it, e.g. handed over on paper."""
        return self._fresh(services.send_invoice(self.get_object(), request.user))

    @extend_schema(request=ReasonSerializer, responses=InvoiceSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request: Request, pk: str | None = None) -> Response:
        ser = ReasonSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        invoice = services.void_invoice(
            self.get_object(), request.user, ser.validated_data.get("reason", "")
        )
        return self._fresh(invoice)

    @extend_schema(request=ReasonSerializer, responses={201: InvoiceSerializer})
    @action(detail=True, methods=["post"])
    def reissue(self, request: Request, pk: str | None = None) -> Response:
        ser = ReasonSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        copy = services.reissue_invoice(
            self.get_object(), request.user, ser.validated_data.get("reason", "")
        )
        res = self._fresh(copy)
        res.status_code = status.HTTP_201_CREATED
        return res

    @extend_schema(request=PaymentSerializer, responses={201: PaymentSerializer})
    @action(detail=True, methods=["post"])
    def payments(self, request: Request, pk: str | None = None) -> Response:
        ser = PaymentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        payment = services.record_payment(self.get_object(), request.user, **ser.validated_data)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=WhatsAppShareSerializer)
    @action(detail=True, methods=["post"])
    def whatsapp(self, request: Request, pk: str | None = None) -> Response:
        """Marks the invoice sent and returns a wa.me link for the owner to open."""
        return Response(share_via_whatsapp(self.get_object(), request.user))

    @extend_schema(request=EmailRequestSerializer, responses={202: DeliverySerializer})
    @action(detail=True, methods=["post"])
    def email(self, request: Request, pk: str | None = None) -> Response:
        invoice = self.get_object()
        ser = EmailRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        to = ser.validated_data.get("to") or invoice.customer.email
        if not to:
            raise ValidationError({"to": "This customer has no email address. Enter one."})
        delivery = queue_email(invoice, request.user, to, ser.validated_data.get("message", ""))
        return Response(DeliverySerializer(delivery).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def pdf(self, request: Request, pk: str | None = None) -> HttpResponse:
        invoice = self.get_object()
        res = HttpResponse(get_or_build_pdf(invoice), content_type="application/pdf")
        res["Content-Disposition"] = f'attachment; filename="{pdf_filename(invoice)}"'
        return res


def _by_currency(qs: QuerySet[Any], field: str) -> list[dict[str, Any]]:
    rows = qs.values("currency").annotate(amount=Sum(field), count=Count("id")).order_by("currency")
    return [
        {"currency": r["currency"], "amount": r["amount"] or 0, "count": r["count"]} for r in rows
    ]


@extend_schema(responses=DashboardSerializer)
@api_view(["GET"])
@permission_classes([HasBusiness])
def dashboard(request: Request) -> Response:
    business = require_business(request)
    today = timezone.localdate()
    invoices = Invoice.objects.filter(business=business)
    outstanding: Any = invoices.outstanding()  # type: ignore[attr-defined]
    month_start = dt.date(today.year, today.month, 1)
    paid_rows = (
        Payment.objects.filter(business=business, paid_on__gte=month_start, paid_on__lte=today)
        .values(currency=F("invoice__currency"))
        .annotate(amount=Sum("amount"), count=Count("id"))
        .order_by("currency")
    )
    debtors = (
        outstanding.values("customer_id", "customer__name", "currency")
        .annotate(owed=Sum("balance_amount"), invoices=Count("id"))
        .order_by("-owed")[:5]
    )
    data = {
        "owed": _by_currency(outstanding, "balance_amount"),
        "overdue": _by_currency(outstanding.filter(due_date__lt=today), "balance_amount"),
        "paid_this_month": [
            {"currency": r["currency"], "amount": r["amount"] or 0, "count": r["count"]}
            for r in paid_rows
        ],
        "drafts": invoices.filter(status=Invoice.Status.DRAFT).count(),
        "top_debtors": [
            {
                "customer_id": d["customer_id"],
                "name": d["customer__name"],
                "currency": d["currency"],
                "balance": d["owed"],
                "invoices": d["invoices"],
            }
            for d in debtors
        ],
        "recent": InvoiceListSerializer(
            invoices.with_balance()
            .select_related("customer")
            .exclude(status=Invoice.Status.VOID)[:5],  # type: ignore[attr-defined]
            many=True,
        ).data,
    }
    return Response(data)
