"""Customer-facing quote page with Accept / Decline. Server-rendered, no JavaScript."""

import uuid

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Membership
from apps.invoices.pdf import document_context, get_or_build_pdf, pdf_filename

from . import services
from .models import Quote


def _load(request: HttpRequest, token: uuid.UUID) -> tuple[Quote, bool]:
    quote = (
        Quote.objects.select_related("business", "customer", "converted_invoice")
        .prefetch_related("lines")
        .filter(public_token=token)
        .first()
    )
    if quote is None:
        raise Http404
    is_member = (
        request.user.is_authenticated
        and Membership.objects.filter(user=request.user, business=quote.business).exists()
    )
    if quote.status == Quote.Status.DRAFT and not is_member:
        raise Http404
    return quote, is_member


def _private(response: HttpResponse) -> HttpResponse:
    response["X-Robots-Tag"] = "noindex, nofollow"
    # same-origin, not no-referrer: with no-referrer browsers send "Origin: null" on the
    # Accept/Decline form POST and Django's CSRF check rejects it. The token in the URL
    # still never leaks to other sites.
    response["Referrer-Policy"] = "same-origin"
    return response


@never_cache
@require_GET
def public_quote(request: HttpRequest, token: uuid.UUID) -> HttpResponse:
    quote, is_member = _load(request, token)
    if not is_member and quote.status == Quote.Status.SENT:
        services.mark_viewed(quote)
    context = {
        **document_context(quote),
        "pdf": False,
        "preview_draft": quote.status == Quote.Status.DRAFT,
        "is_member": is_member,
        "error": request.GET.get("error"),
    }
    return _private(render(request, "quotes/document.html", context))


@require_POST
def public_quote_respond(request: HttpRequest, token: uuid.UUID) -> HttpResponse:
    quote, is_member = _load(request, token)
    if is_member:  # owners record answers from the app, not by clicking the customer's button
        return redirect(quote.public_path)
    decision = request.POST.get("decision")
    if decision not in ("accept", "decline"):
        return redirect(quote.public_path)
    try:
        services.respond(quote, accepted=decision == "accept")
    except ValidationError:
        return redirect(quote.public_path + "?error=closed")
    return redirect(quote.public_path)


@never_cache
@require_GET
def public_quote_pdf(request: HttpRequest, token: uuid.UUID) -> HttpResponse:
    quote, _ = _load(request, token)
    response = HttpResponse(get_or_build_pdf(quote), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{pdf_filename(quote)}"'
    return _private(response)
