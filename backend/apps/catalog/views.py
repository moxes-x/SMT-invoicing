from rest_framework import filters, viewsets

from apps.core.tenancy import BusinessScopedMixin, HasBusiness

from .models import Item
from .serializers import ItemSerializer


class ItemViewSet(BusinessScopedMixin, viewsets.ModelViewSet[Item]):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer
    permission_classes = [HasBusiness]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "description"]
    lookup_value_regex = r"\d+"
