"""Customer-facing payment pages: Pay now on an invoice, the waiting page, and receipts."""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from rest_framework.exceptions import ValidationError

from apps.core.validators import normalize_phone
from apps.invoices.models import Invoice
from apps.invoices.public import _load, _private, page_context

from . import lenco, online
from .models import LencoAccount, Payment, PaymentAttempt
from .receipts import get_or_build_receipt_pdf, receipt_context


@require_POST
def pay(request: HttpRequest, token: uuid.UUID) -> HttpResponse:
    invoice, is_member = _load(request, token)
    if is_member or not online.can_pay_online(invoice):
        return redirect(invoice.public_path)

    def again(error: str) -> HttpResponse:
        ctx = page_context(invoice, is_member, pay_error=error)
        if request.POST.get("phone"):
            ctx["pay_phone"] = request.POST["phone"]
        if request.POST.get("operator"):
            ctx["operator"] = request.POST["operator"]
        return _private(render(request, "invoices/document.html", ctx, status=400))

    try:
        if request.POST.get("method") == "card":
            email = request.POST.get("email", "").strip()
            if "@" not in email:
                return again("Enter your email address for the card receipt.")
            attempt = online.start_card(invoice, email=email)
        else:
            try:
                phone = normalize_phone(request.POST.get("phone", ""))
            except DjangoValidationError:
                return again("Enter a valid Zambian mobile money number.")
            attempt = online.start_mobile_money(
                invoice, phone=phone, operator=request.POST.get("operator", "")
            )
    except ValidationError as exc:
        detail: Any = exc.detail
        if isinstance(detail, dict):
            detail = next(iter(detail.values()))
        if isinstance(detail, list):
            detail = detail[0]
        return again(str(detail))
    return redirect(f"{invoice.public_path}pay/{attempt.reference}/")


@never_cache
@require_GET
def pay_status(request: HttpRequest, token: uuid.UUID, reference: str) -> HttpResponse:
    invoice, _ = _load(request, token)
    attempt = PaymentAttempt.objects.filter(invoice=invoice, reference=reference).first()
    if attempt is None:
        raise Http404
    # Card attempts are checked once the widget says it's done (?check=1), so an untouched
    # widget doesn't make us call Lenco on every refresh.
    if attempt.channel == PaymentAttempt.Channel.MOBILE_MONEY or request.GET.get("check"):
        attempt = online.refresh(attempt)
    account = LencoAccount.objects.filter(business=invoice.business).first()
    invoice = Invoice.objects.with_balance().get(pk=invoice.pk)  # type: ignore[attr-defined]
    context: dict[str, Any] = {
        "invoice": invoice,
        "business": invoice.business,
        "customer": invoice.customer,
        "attempt": attempt,
        "account": account,
        "pdf": False,
        "checking": request.GET.get("check") == "1",
    }
    if account and attempt.channel == PaymentAttempt.Channel.CARD:
        names = invoice.customer.name.split() or [""]
        context["widget"] = {
            "key": account.public_key,
            "reference": attempt.reference,
            "email": attempt.email,
            "amount": lenco.to_major(attempt.amount),
            "currency": attempt.currency,
            "channels": ["card"],
            "label": f"{invoice.business.name} {invoice.number}",
            "customer": {
                "firstName": names[0],
                "lastName": " ".join(names[1:]) or names[0],
                "phone": invoice.customer.phone,
            },
        }
    return _private(render(request, "payments/status.html", context))


def _load_receipt(token: uuid.UUID) -> Payment:
    payment = (
        Payment.objects.select_related("business", "invoice__customer")
        .filter(public_token=token)
        .first()
    )
    if payment is None:
        raise Http404
    return payment


@never_cache
@require_GET
def public_receipt(request: HttpRequest, token: uuid.UUID) -> HttpResponse:
    payment = _load_receipt(token)
    return _private(render(request, "payments/receipt.html", receipt_context(payment)))


@never_cache
@require_GET
def public_receipt_pdf(request: HttpRequest, token: uuid.UUID) -> HttpResponse:
    payment = _load_receipt(token)
    response = HttpResponse(get_or_build_receipt_pdf(payment), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="{payment.receipt_number or "receipt"}.pdf"'
    )
    return _private(response)
