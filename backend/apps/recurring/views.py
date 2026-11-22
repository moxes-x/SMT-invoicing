from rest_framework import viewsets

from apps.core.tenancy import BusinessScopedMixin, HasBusiness

from .models import RecurringInvoice
from .serializers import RecurringInvoiceSerializer


class RecurringInvoiceViewSet(BusinessScopedMixin, viewsets.ModelViewSet[RecurringInvoice]):
    """Schedules. Deleting one keeps the invoices it already made."""

    queryset = RecurringInvoice.objects.select_related("customer")
    serializer_class = RecurringInvoiceSerializer
    permission_classes = [HasBusiness]
    lookup_value_regex = r"\d+"

    def perform_create(self, serializer: RecurringInvoiceSerializer) -> None:  # type: ignore[override]
        serializer.save()
