from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.accounts.views import BusinessViewSet
from apps.catalog.views import ItemViewSet
from apps.customers.views import CustomerViewSet
from apps.invoices import public
from apps.invoices.views import InvoiceViewSet, dashboard
from apps.payments.views import PaymentViewSet

router = DefaultRouter()
router.register("businesses", BusinessViewSet, basename="business")
router.register("customers", CustomerViewSet, basename="customer")
router.register("items", ItemViewSet, basename="item")
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("payments", PaymentViewSet, basename="payment")

urlpatterns = [
    path(f"{settings.ADMIN_URL}", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/dashboard/", dashboard, name="dashboard"),
    path("api/", include(router.urls)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("i/<uuid:token>/", public.public_invoice, name="public-invoice"),
    path("i/<uuid:token>/pdf/", public.public_invoice_pdf, name="public-invoice-pdf"),
]
