from typing import Any, cast

from django.contrib.auth import login, logout
from django.db import transaction
from django.db.models import QuerySet
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .middleware import SESSION_KEY, get_current_business
from .models import Business, Membership, User
from .serializers import (
    BusinessSerializer,
    LoginSerializer,
    MeSerializer,
    SignupSerializer,
    UserSerializer,
)


def me_payload(request: Request, user: User | None = None) -> dict[str, Any]:
    user = user or cast(User, request.user)
    businesses = Business.objects.filter(memberships__user=user).order_by("name")
    data = {
        "user": user,
        "current_business": get_current_business(request),
        "businesses": businesses,
    }
    return MeSerializer(data, context={"request": request}).data


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(APIView):
    """GET this once on app load so the browser has a csrftoken cookie for later POSTs."""

    permission_classes = [AllowAny]

    @extend_schema(responses={204: None})
    def get(self, request: Request) -> Response:
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_protect, name="dispatch")
class SignupView(APIView):
    """DRF skips CSRF for anonymous users; we enforce it here to block login/signup CSRF."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(request=SignupSerializer, responses={201: MeSerializer})
    def post(self, request: Request) -> Response:
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request._request, user, backend="django.contrib.auth.backends.ModelBackend")
        request.user = user
        return Response(me_payload(request, user), status=status.HTTP_201_CREATED)


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(request=LoginSerializer, responses={200: MeSerializer})
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data, context={"request": request._request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        login(request._request, user)
        request.user = user
        return Response(me_payload(request, user))


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MeSerializer)
    def get(self, request: Request) -> Response:
        return Response(me_payload(request))

    @extend_schema(request=UserSerializer, responses=MeSerializer)
    def patch(self, request: Request) -> Response:
        """Change your own name or app language."""
        ser = UserSerializer(cast(User, request.user), data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(me_payload(request))


class BusinessViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet[Business],
):
    """Businesses the user belongs to. Others are invisible (404), never forbidden (403)."""

    queryset = Business.objects.none()  # for schema introspection; real scope in get_queryset
    serializer_class = BusinessSerializer
    permission_classes = [IsAuthenticated]
    lookup_value_regex = r"\d+"

    def get_queryset(self) -> QuerySet[Business]:
        return Business.objects.filter(memberships__user=cast(User, self.request.user)).order_by(
            "name"
        )

    @transaction.atomic
    def perform_create(self, serializer: BusinessSerializer) -> None:  # type: ignore[override]
        business = serializer.save()
        Membership.objects.create(
            user=cast(User, self.request.user), business=business, role=Membership.Role.OWNER
        )
        self.request.session[SESSION_KEY] = business.pk

    def perform_update(self, serializer: BusinessSerializer) -> None:  # type: ignore[override]
        role = (
            Membership.objects.filter(
                user=cast(User, self.request.user), business=serializer.instance
            )
            .values_list("role", flat=True)
            .first()
        )
        if role not in (Membership.Role.OWNER, Membership.Role.ADMIN):
            raise PermissionDenied("Only owners and admins can edit the business profile.")
        serializer.save()

    @extend_schema(request=None, responses=MeSerializer)
    @action(detail=True, methods=["post"])
    def switch(self, request: Request, pk: str | None = None) -> Response:
        business = self.get_object()  # 404 if not a member
        request.session[SESSION_KEY] = business.pk
        return Response(me_payload(request))
