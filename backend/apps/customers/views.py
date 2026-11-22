from django.db.models import ProtectedError, QuerySet
from rest_framework import filters, status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.tenancy import BusinessScopedMixin, HasBusiness

from .models import Customer
from .serializers import CustomerSerializer


class CustomerViewSet(BusinessScopedMixin, viewsets.ModelViewSet[Customer]):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [HasBusiness]
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
