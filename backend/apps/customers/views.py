import datetime as dt
from typing import Any

from django.db.models import ProtectedError, QuerySet
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.text import slugify
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import filters, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.tenancy import BusinessScopedMixin, HasBusiness
from apps.core.time import today
from apps.invoices.statements import Statement, build_statement, outstanding_invoices
from apps.payments.views import parse_range

from .models import Customer
from .serializers import CustomerSerializer


class StatementRowSerializer(serializers.Serializer[Any]):
    date = serializers.DateField()
    kind = serializers.ChoiceField(choices=["invoice", "payment"])
    reference = serializers.CharField()
    description = serializers.CharField()
    debit = serializers.IntegerField()
    credit = serializers.IntegerField()
    balance = serializers.IntegerField()
    invoice_id = serializers.IntegerField(allow_null=True)


class StatementSerializer(serializers.Serializer[Any]):
    currency = serializers.CharField()
    start = serializers.DateField()
    end = serializers.DateField()
    opening = serializers.IntegerField()
    invoiced = serializers.IntegerField()
    paid = serializers.IntegerField()
    closing = serializers.IntegerField()
    rows = StatementRowSerializer(many=True)


STATEMENT_PARAMS = [
    OpenApiParameter("start", OpenApiTypes.DATE, description="Default: 90 days ago"),
    OpenApiParameter("end", OpenApiTypes.DATE, description="Default: today"),
    OpenApiParameter(
        "currency", str, enum=["ZMW", "USD"], description="Default: business currency"
    ),
]


def _statement(view: Any, request: Request) -> Statement:
    customer = view.get_object()
    start, end = parse_range(request)
    end = end or today()
    start = start or end - dt.timedelta(days=90)
    if start > end:
        raise serializers.ValidationError({"start": "Start must be before the end."})
    currency = request.query_params.get("currency") or customer.business.default_currency
    if currency not in ("ZMW", "USD"):
        raise serializers.ValidationError({"currency": "Use ZMW or USD."})
    return build_statement(customer, currency, start, end)


class CustomerViewSet(BusinessScopedMixin, viewsets.ModelViewSet[Customer]):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [HasBusiness]
    manager_actions = ("destroy",)
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "phone", "email"]
    ordering_fields = ["name", "created_at"]
    lookup_value_regex = r"\d+"

    def get_queryset(self) -> QuerySet[Customer]:
        return super().get_queryset()

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"detail": "This customer has invoices and can't be deleted."},
                status=status.HTTP_409_CONFLICT,
            )

    @extend_schema(parameters=STATEMENT_PARAMS, responses=StatementSerializer)
    @action(detail=True, methods=["get"])
    def statement(self, request: Request, pk: str | None = None) -> Response:
        """Opening balance, invoices and payments in the period, running and closing balance."""
        return Response(StatementSerializer(_statement(self, request)).data)

    @extend_schema(
        parameters=STATEMENT_PARAMS, responses={(200, "application/pdf"): OpenApiTypes.BINARY}
    )
    @action(detail=True, methods=["get"], url_path="statement/pdf")
    def statement_pdf(self, request: Request, pk: str | None = None) -> HttpResponse:
        from weasyprint import HTML

        st = _statement(self, request)
        html = render_to_string(
            "statements/statement.html",
            {
                "statement": st,
                "customer": st.customer,
                "business": st.customer.business,
                "outstanding": outstanding_invoices(st.customer, st.currency),
                "pdf": True,
            },
        )
        response = HttpResponse(HTML(string=html).write_pdf(), content_type="application/pdf")
        name = f"statement-{slugify(st.customer.name) or st.customer.pk}-{st.end.isoformat()}.pdf"
        response["Content-Disposition"] = f'inline; filename="{name}"'
        return response
