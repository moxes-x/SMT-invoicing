from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.accounts import team
from apps.accounts.views import BusinessViewSet
from apps.catalog.views import ItemViewSet
from apps.customers.views import CustomerViewSet
from apps.fiscal.views import test_zra_device, zra_device
from apps.invoices import public, reports
from apps.invoices.views import InvoiceViewSet, app_config, dashboard
from apps.messaging.webhooks import whatsapp_webhook
from apps.payments import public as pay_public
from apps.payments.views import PaymentViewSet, online_payments, test_online_payments
from apps.payments.webhooks import lenco_webhook
from apps.quotes import public as quote_public
from apps.quotes.views import QuoteViewSet
from apps.recurring.views import RecurringInvoiceViewSet

router = DefaultRouter()
router.register("businesses", BusinessViewSet, basename="business")
router.register("customers", CustomerViewSet, basename="customer")
router.register("items", ItemViewSet, basename="item")
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("payments", PaymentViewSet, basename="payment")
router.register("quotes", QuoteViewSet, basename="quote")
router.register("recurring", RecurringInvoiceViewSet, basename="recurring")

urlpatterns = [
    path(f"{settings.ADMIN_URL}", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/dashboard/", dashboard, name="dashboard"),
    path("api/config/", app_config, name="config"),
    path("api/reports/", reports.report, name="report"),
    path("api/reports/export/", reports.report_csv, name="report-export"),
    path("api/team/", team.team, name="team"),
    path("api/team/invites/", team.invite, name="team-invite"),
    path("api/team/invites/<int:pk>/", team.revoke_invite, name="team-invite-revoke"),
    path("api/team/members/<int:pk>/", team.member, name="team-member"),
    path("api/online-payments/", online_payments, name="online-payments"),
    path("api/online-payments/test/", test_online_payments, name="online-payments-test"),
    path("api/zra/", zra_device, name="zra-device"),
    path("api/zra/test/", test_zra_device, name="zra-device-test"),
    path("api/webhooks/whatsapp/", whatsapp_webhook, name="whatsapp-webhook"),
    path("api/webhooks/lenco/<uuid:webhook_id>/", lenco_webhook, name="lenco-webhook"),
    # Email provider tracking webhooks (anymail), e.g. /api/webhooks/email/resend/tracking/
    path("api/webhooks/email/", include("anymail.urls")),
    path("api/", include(router.urls)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("i/<uuid:token>/", public.public_invoice, name="public-invoice"),
    path("i/<uuid:token>/pdf/", public.public_invoice_pdf, name="public-invoice-pdf"),
    path("i/<uuid:token>/pay/", pay_public.pay, name="public-invoice-pay"),
    path(
        "i/<uuid:token>/pay/<str:reference>/",
        pay_public.pay_status,
        name="public-invoice-pay-status",
    ),
    path("r/<uuid:token>/", pay_public.public_receipt, name="public-receipt"),
    path("r/<uuid:token>/pdf/", pay_public.public_receipt_pdf, name="public-receipt-pdf"),
    path("q/<uuid:token>/", quote_public.public_quote, name="public-quote"),
    path("q/<uuid:token>/respond/", quote_public.public_quote_respond, name="public-quote-respond"),
    path("q/<uuid:token>/pdf/", quote_public.public_quote_pdf, name="public-quote-pdf"),
]
