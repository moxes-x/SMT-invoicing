"""The team: who can use a business, with which role, and email invites to join."""

from __future__ import annotations

from typing import Any, cast

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.tenancy import HasBusiness, require_business, require_manager

from .middleware import SESSION_KEY
from .models import MANAGER_ROLES, Invite, Membership, User

NEEDS_OWNER = "A business needs an owner. Make someone else owner first."
INVITE_CLOSED = "This invite has expired or was already used. Ask for a new one."

ROLE_HELP = {
    "owner": "Everything, including the team",
    "admin": "Everything except changing owners",
    "staff": "Customers, invoices, quotes and payments",
    "accountant": "Sees everything and exports; changes nothing",
}


class TeamMemberSerializer(serializers.ModelSerializer[Membership]):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    is_you = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = ["id", "email", "full_name", "role", "is_you", "created_at"]

    def get_is_you(self, obj: Membership) -> bool:
        return bool(obj.user_id == self.context["request"].user.pk)


def join_link(inv: Invite) -> str:
    return settings.PUBLIC_BASE_URL.rstrip("/") + f"/join/{inv.token}"


class InviteSerializer(serializers.ModelSerializer[Invite]):
    invited_by = serializers.CharField(source="invited_by.email", read_only=True, default="")
    link = serializers.SerializerMethodField(help_text="Share it on WhatsApp if email is slow.")

    class Meta:
        model = Invite
        fields = ["id", "email", "role", "invited_by", "created_at", "expires_at", "link"]
        read_only_fields = ["id", "invited_by", "created_at", "expires_at"]

    def get_link(self, obj: Invite) -> str:
        return join_link(obj)


class TeamSerializer(serializers.Serializer[Any]):
    members = TeamMemberSerializer(many=True)
    invites = InviteSerializer(many=True)


class RoleSerializer(serializers.Serializer[Any]):
    role = serializers.ChoiceField(choices=Membership.Role.choices)


class InviteInfoSerializer(serializers.Serializer[Any]):
    business = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField()
    invited_by = serializers.CharField()
    is_open = serializers.BooleanField()


def _team(request: Request) -> dict[str, Any]:
    business = require_business(request)
    # Open invites carry join links, so only the people who manage the team see them.
    invites = (
        [i for i in business.invites.select_related("invited_by") if i.is_open]
        if getattr(request, "role", None) in MANAGER_ROLES
        else []
    )
    return TeamSerializer(
        {
            "members": business.memberships.select_related("user").order_by("created_at"),
            "invites": invites,
        },
        context={"request": request},
    ).data


def _check_can_assign(request: Request, role: str) -> None:
    """Admins manage the team but can't create, change or remove owners."""
    require_manager(request)
    if role == Membership.Role.OWNER and request.role != Membership.Role.OWNER:  # type: ignore[attr-defined]
        raise PermissionDenied("Only an owner can make someone an owner.")


@extend_schema(responses=TeamSerializer)
@api_view(["GET"])
@permission_classes([HasBusiness])
def team(request: Request) -> Response:
    return Response(_team(request))


@extend_schema(request=InviteSerializer, responses=TeamSerializer)
@api_view(["POST"])
@permission_classes([HasBusiness])
def invite(request: Request) -> Response:
    business = require_business(request)
    ser = InviteSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    email = ser.validated_data["email"].lower()
    role = ser.validated_data["role"]
    _check_can_assign(request, role)
    if business.memberships.filter(user__email__iexact=email).exists():
        raise ValidationError({"email": "This person is already on the team."})
    # Re-inviting replaces any earlier open invite for the same email.
    business.invites.filter(email__iexact=email, accepted_at__isnull=True).delete()
    inv = Invite.objects.create(
        business=business, email=email, role=role, invited_by=cast(User, request.user)
    )
    link = join_link(inv)
    inviter = request.user.full_name or request.user.email  # type: ignore[union-attr]
    send_mail(
        f"{inviter} invited you to {business.name}",
        f"{inviter} invited you to help run {business.name} as {inv.get_role_display().lower()} "
        f"({ROLE_HELP[role].lower()}).\n\nJoin here (the link works for 7 days): {link}\n\n"
        f"Sign up or log in with {email} to accept.",
        settings.DEFAULT_FROM_EMAIL,
        [email],
    )
    return Response(_team(request), status=status.HTTP_201_CREATED)


@extend_schema(request=None, responses=TeamSerializer)
@api_view(["DELETE"])
@permission_classes([HasBusiness])
def revoke_invite(request: Request, pk: int) -> Response:
    require_manager(request)
    deleted, _ = require_business(request).invites.filter(pk=pk).delete()
    if not deleted:
        raise NotFound()
    return Response(_team(request))


def _owners(business: Any) -> int:
    return int(business.memberships.filter(role=Membership.Role.OWNER).count())


@extend_schema(methods=["PATCH"], request=RoleSerializer, responses=TeamSerializer)
@extend_schema(methods=["DELETE"], request=None, responses=TeamSerializer)
@api_view(["PATCH", "DELETE"])
@permission_classes([HasBusiness])
@transaction.atomic
def member(request: Request, pk: int) -> Response:
    business = require_business(request)
    m = business.memberships.select_for_update().filter(pk=pk).first()
    if m is None:
        raise NotFound()
    is_self = m.user_id == request.user.pk
    if request.method == "DELETE":
        if not is_self:  # anyone may leave; removing others needs a manager
            _check_can_assign(request, m.role)
        if m.role == Membership.Role.OWNER and _owners(business) == 1:
            raise ValidationError({"detail": NEEDS_OWNER})
        m.delete()
        if is_self:
            request.session.pop(SESSION_KEY, None)
            return Response({"members": [], "invites": []})
        return Response(_team(request))
    ser = RoleSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    role = ser.validated_data["role"]
    _check_can_assign(request, m.role)  # admins can't touch owners
    _check_can_assign(request, role)  # …or create them
    if m.role == Membership.Role.OWNER and role != m.role and _owners(business) == 1:
        raise ValidationError({"detail": NEEDS_OWNER})
    m.role = role
    m.save(update_fields=["role"])
    return Response(_team(request))


def _open_invite(token: str) -> Invite:
    inv = Invite.objects.select_related("business", "invited_by").filter(token=token).first()
    if inv is None:
        raise NotFound("This invite link isn't valid.")
    return inv


@extend_schema(responses=InviteInfoSerializer)
@api_view(["GET"])
@permission_classes([AllowAny])
def invite_info(request: Request, token: str) -> Response:
    """Shown on the join page before signing up or logging in."""
    inv = _open_invite(token)
    return Response(
        InviteInfoSerializer(
            {
                "business": inv.business.name,
                "email": inv.email,
                "role": inv.role,
                "invited_by": (inv.invited_by.full_name or inv.invited_by.email)
                if inv.invited_by
                else "",
                "is_open": inv.is_open,
            }
        ).data
    )


@extend_schema(request=None, responses={204: None})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def accept_invite(request: Request, token: str) -> Response:
    inv = _open_invite(token)
    if not inv.is_open:
        raise ValidationError({"detail": INVITE_CLOSED})
    user = cast(User, request.user)
    if user.email.lower() != inv.email.lower():
        raise PermissionDenied(f"This invite is for {inv.email}. Log in with that email to accept.")
    Membership.objects.get_or_create(user=user, business=inv.business, defaults={"role": inv.role})
    inv.accepted_at = timezone.now()
    inv.save(update_fields=["accepted_at"])
    request.session[SESSION_KEY] = inv.business_id
    return Response(status=status.HTTP_204_NO_CONTENT)
