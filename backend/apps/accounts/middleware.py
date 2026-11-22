from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from .models import Business

SESSION_KEY = "current_business_id"


def get_current_business(request: HttpRequest) -> Business | None:
    """The business the logged-in user is acting for.

    Uses the id stored in the session if the user is still a member of it, otherwise falls back
    to the user's oldest membership. Never trusts a client-supplied id without a membership check.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    qs = Business.objects.filter(memberships__user=user)
    business_id = request.session.get(SESSION_KEY)
    if business_id is not None:
        business = qs.filter(pk=business_id).first()
        if business is not None:
            return business
    return qs.order_by("memberships__created_at", "pk").first()


class CurrentBusinessMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Resolved after AuthenticationMiddleware, so request.user is already the session user.
        request.business = get_current_business(request)  # type: ignore[attr-defined]
        return self.get_response(request)
