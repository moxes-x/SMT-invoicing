from typing import Any

from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.tenancy import BusinessScopedMixin, HasBusiness
from apps.invoices.pdf import get_or_build_pdf, pdf_filename
from apps.invoices.serializers import InvoiceRefSerializer
from apps.messaging.models import Delivery
from apps.messaging.serializers import SendRequestSerializer, SendResultSerializer
from apps.messaging.services import dispatch

from . import services
from .models import Quote
from .serializers import ConvertSerializer, QuoteListSerializer, QuoteSerializer, RespondSerializer

STATUS_FILTERS = ["draft", "sent", "accepted", "declined", "expired", "converted", "open"]


@extend_schema(parameters=[OpenApiParameter("status", str, enum=STATUS_FILTERS)])
class QuoteViewSet(
    BusinessScopedMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet[Quote],
):
    queryset = Quote.objects.all()
    permission_classes = [HasBusiness]
    filter_backends = [filters.SearchFilter]
    search_fields = ["number", "customer__name"]
    lookup_value_regex = r"\d+"

    def get_serializer_class(self) -> Any:
        return QuoteListSerializer if self.action == "list" else QuoteSerializer

    def get_queryset(self) -> Any:
        qs: Any = super().get_queryset().select_related("customer", "business")
        if self.action != "list":
            qs = qs.select_related("converted_invoice").prefetch_related(
                "lines", "deliveries", "activity__actor"
            )
        value = self.request.query_params.get("status")
        today = timezone.localdate()
        match value:
            case None | "":
                return qs
            case "expired":
                return qs.filter(status=Quote.Status.SENT, valid_until__lt=today)
            case "sent":
                return qs.filter(status=Quote.Status.SENT, valid_until__gte=today)
            case "open":  # waiting on the customer or on you
                return qs.filter(
                    status__in=[Quote.Status.DRAFT, Quote.Status.SENT, Quote.Status.ACCEPTED]
                )
            case "draft" | "accepted" | "declined" | "converted":
                return qs.filter(status=value)
        raise ValidationError({"status": f"Use one of: {', '.join(STATUS_FILTERS)}."})

    def perform_create(self, serializer: Any) -> None:
        serializer.save()

    def _fresh(self, quote: Quote) -> Response:
        obj = self.get_queryset().get(pk=quote.pk)
        return Response(QuoteSerializer(obj, context=self.get_serializer_context()).data)

    @extend_schema(request=None, responses=QuoteSerializer)
    @action(detail=True, methods=["post"])
    def send(self, request: Request, pk: str | None = None) -> Response:
        return self._fresh(services.send_quote(self.get_object(), request.user))

    @extend_schema(request=SendRequestSerializer, responses=SendResultSerializer)
    @action(detail=True, methods=["post"])
    def deliver(self, request: Request, pk: str | None = None) -> Response:
        ser = SendRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = dispatch(self.get_object(), request.user, Delivery.Kind.QUOTE, ser.validated_data)
        code = status.HTTP_200_OK if "url" in result else status.HTTP_202_ACCEPTED
        return Response(result, status=code)

    @extend_schema(request=RespondSerializer, responses=QuoteSerializer)
    @action(detail=True, methods=["post"])
    def respond(self, request: Request, pk: str | None = None) -> Response:
        """Record the customer's answer on their behalf (e.g. they said yes on the phone)."""
        ser = RespondSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        quote = services.respond(self.get_object(), ser.validated_data["accepted"], request.user)
        return self._fresh(quote)

    @extend_schema(request=ConvertSerializer, responses={201: InvoiceRefSerializer})
    @action(detail=True, methods=["post"])
    def convert(self, request: Request, pk: str | None = None) -> Response:
        ser = ConvertSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        invoice = services.convert_to_invoice(self.get_object(), request.user, **ser.validated_data)
        return Response({"id": invoice.pk, "number": invoice.number}, status=201)

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def pdf(self, request: Request, pk: str | None = None) -> HttpResponse:
        quote = self.get_object()
        res = HttpResponse(get_or_build_pdf(quote), content_type="application/pdf")
        res["Content-Disposition"] = f'attachment; filename="{pdf_filename(quote)}"'
        return res
