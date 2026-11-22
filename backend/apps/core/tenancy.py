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


SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


class HasBusiness(BasePermission):
    """Member of the current business, with role-based access:

    - accountants read everything (and export) but change nothing;
    - staff can also create and edit;
    - actions a view lists in `manager_actions` (void, delete, …) need an owner or admin.
    """

    message = "Create or join a business first."

    def has_permission(self, request: Request, view: APIView) -> bool:
        from apps.accounts.models import MANAGER_ROLES, WRITE_ROLES

        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request, "business", None) is None:
            return False
        role = getattr(request, "role", None)
        if request.method in SAFE_METHODS:
            return True
        if getattr(view, "action", None) in getattr(view, "manager_actions", ()):
            if role not in MANAGER_ROLES:
                raise PermissionDenied("Only the owner or an admin can do this.")
            return True
        if role not in WRITE_ROLES:
            raise PermissionDenied("Your role can view but not change things.")
        return True


def require_manager(request: Request) -> None:
    from apps.accounts.models import MANAGER_ROLES

    if getattr(request, "role", None) not in MANAGER_ROLES:
        raise PermissionDenied("Only the owner or an admin can do this.")


class BusinessScopedMixin:
    """Filters every queryset by request.business and stamps it on create.

    Objects of other businesses are simply invisible, so detail routes return 404 (not 403),
    which avoids leaking whether an id exists.
    """

    business_field = "business"

    def get_queryset(self) -> models.QuerySet[Any]:
        qs = super().get_queryset()  # type: ignore[misc]
        return qs.filter(**{self.business_field: require_business(self.request)})  # type: ignore[attr-defined]

    def perform_create(self, serializer: Any) -> None:
        serializer.save(**{self.business_field: require_business(self.request)})  # type: ignore[attr-defined]
