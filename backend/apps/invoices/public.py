"""Customer-facing pages: server-rendered, no JavaScript, light on data, WhatsApp-browser safe."""

import uuid

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.models import Membership

from .models import Invoice
from .pdf import document_context, get_or_build_pdf, pdf_filename
from .services import mark_viewed


def _load(request: HttpRequest, token: uuid.UUID) -> tuple[Invoice, bool]:
    invoice = (
        Invoice.objects.with_balance()  # type: ignore[attr-defined]
        .select_related("business", "customer", "reissued_as")
        .prefetch_related("lines", "payments")
        .filter(public_token=token)
        .first()
    )
    if invoice is None:
        raise Http404
    is_member = (
        request.user.is_authenticated
        and Membership.objects.filter(user=request.user, business=invoice.business).exists()
    )
    if invoice.status == Invoice.Status.DRAFT and not is_member:
        raise Http404  # drafts aren't public until sent
    return invoice, is_member


def _private(response: HttpResponse) -> HttpResponse:
    response["X-Robots-Tag"] = "noindex, nofollow"
    # same-origin, not no-referrer: with no-referrer browsers send "Origin: null" on the Pay now
    # form POST and Django's CSRF check rejects it. The token still never leaks to other sites.
    response["Referrer-Policy"] = "same-origin"
    return response


@never_cache
@require_GET
def public_invoice(request: HttpRequest, token: uuid.UUID) -> HttpResponse:
    invoice, is_member = _load(request, token)
    if not is_member and invoice.status == Invoice.Status.SENT:
        mark_viewed(invoice)
    return _private(render(request, "invoices/document.html", page_context(invoice, is_member)))


def page_context(invoice: Invoice, is_member: bool, **extra: object) -> dict[str, object]:
    from apps.payments.lenco import guess_operator, local_phone
    from apps.payments.models import PaymentAttempt
    from apps.payments.online import can_pay_online

    phone = invoice.customer.phone or ""
    return {
        **document_context(invoice),
        "pdf": False,
        "preview_draft": invoice.status == Invoice.Status.DRAFT,
        # Owners see the page as the customer would, minus a working Pay button for themselves.
        "can_pay_online": not is_member and can_pay_online(invoice),
        "operators": PaymentAttempt.Operator.choices,
        "operator": guess_operator(phone) or "mtn",
        "pay_phone": local_phone(phone) if phone else "",
        **extra,
    }


@never_cache
@require_GET
def public_invoice_pdf(request: HttpRequest, token: uuid.UUID) -> HttpResponse:
    invoice, is_member = _load(request, token)
    if not is_member and invoice.status == Invoice.Status.SENT:
        mark_viewed(invoice)
    response = HttpResponse(get_or_build_pdf(invoice), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{pdf_filename(invoice)}"'
    return _private(response)
