"""Tenant isolation helpers. Every business-owned API view must go through these."""

from typing import Any

from django.db import models
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.accounts.models import Business


def require_business(request: Request) -> Business:
    business = getattr(request, "business", None)
    if business is None:
        raise PermissionDenied("Create or join a business first.")
    return business


class HasBusiness(BasePermission):
    message = "Create or join a business first."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(
            request.user and request.user.is_authenticated and getattr(request, "business", None)
        )


class BusinessScopedMixin:
    """Filters every queryset by request.business and stamps it on create.

    Objects of other businesses are simply invisible, so detail routes return 404 (not 403),
    which avoids leaking whether an id exists.
    """

    request: Request
    business_field = "business"

    def get_queryset(self) -> models.QuerySet[Any]:
        qs = super().get_queryset()  # type: ignore[misc]
        return qs.filter(**{self.business_field: require_business(self.request)})

    def perform_create(self, serializer: Any) -> None:
        serializer.save(**{self.business_field: require_business(self.request)})
