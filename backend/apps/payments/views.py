from rest_framework import mixins, viewsets
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.tenancy import BusinessScopedMixin, HasBusiness
from apps.invoices.services import delete_payment

from .models import Payment
from .serializers import PaymentSerializer


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
    lookup_value_regex = r"\d+"

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        delete_payment(self.get_object(), request.user)
        return Response(status=204)
