import datetime as dt

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.middleware import SESSION_KEY
from apps.accounts.models import Invite, Membership

from .factories import CustomerFactory, MembershipFactory, UserFactory, make_invoice

pytestmark = pytest.mark.django_db


def login_as(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def team(owner_a):
    """One member of each role in business A, each with a logged-in client."""
    b = owner_a.business
    members = {"owner": owner_a}
    for role in ("admin", "staff", "accountant"):
        members[role] = MembershipFactory(business=b, role=role)
    return {role: (m, login_as(m.user)) for role, m in members.items()}


class TestRolePermissions:
    def test_accountant_reads_and_exports_but_changes_nothing(self, team, owner_a):
        _, c = team["accountant"]
        make_invoice(owner_a.business)
        assert c.get("/api/invoices/").status_code == 200
        assert c.get("/api/customers/").status_code == 200
        assert c.get("/api/invoices/export/").status_code == 200
        assert c.get("/api/payments/export/").status_code == 200
        res = c.post("/api/customers/", {"name": "Nope"}, format="json")
        assert res.status_code == 403
        assert "view but not change" in res.json()["detail"]
        assert (
            c.post("/api/items/", {"name": "X", "unit_price": 1}, format="json").status_code == 403
        )

    def test_staff_creates_and_sends_but_cannot_void_or_delete(self, team, owner_a):
        _, c = team["staff"]
        b = owner_a.business
        assert c.post("/api/customers/", {"name": "Mwila"}, format="json").status_code == 201
        inv = make_invoice(b, send=True)
        res = c.post(f"/api/invoices/{inv.id}/void/", {"reason": "x"}, format="json")
        assert res.status_code == 403
        assert "owner or an admin" in res.json()["detail"]
        customer = CustomerFactory(business=b)
        assert c.delete(f"/api/customers/{customer.id}/").status_code == 403
        assert c.get("/api/team/").status_code == 200
        assert (
            c.post("/api/team/invites/", {"email": "x@example.com", "role": "staff"}).status_code
            == 403
        )

    def test_admin_can_void(self, team, owner_a):
        _, c = team["admin"]
        inv = make_invoice(owner_a.business, send=True)
        res = c.post(f"/api/invoices/{inv.id}/void/", {"reason": "typo"}, format="json")
        assert res.status_code == 200
        assert res.json()["status"] == "void"

    def test_only_managers_change_business_settings(self, team, owner_a):
        url = f"/api/businesses/{owner_a.business.id}/"
        for role in ("staff", "accountant"):
            assert team[role][1].patch(url, {"name": "X"}, format="json").status_code == 403
        assert team["admin"][1].patch(url, {"name": "Y"}, format="json").status_code == 200

    def test_me_reports_role(self, team):
        me = team["accountant"][1].get("/api/auth/me/").json()
        assert me["current_business"]["role"] == "accountant"


class TestTeamManagement:
    def test_team_lists_members_and_open_invites(self, team, owner_a):
        _, c = team["owner"]
        c.post("/api/team/invites/", {"email": "New@Example.com", "role": "staff"}, format="json")
        data = c.get("/api/team/").json()
        assert {m["role"] for m in data["members"]} == {"owner", "admin", "staff", "accountant"}
        assert [m["is_you"] for m in data["members"]].count(True) == 1
        assert [i["email"] for i in data["invites"]] == ["new@example.com"]
        token = Invite.objects.get().token
        assert data["invites"][0]["link"] == f"https://app.example.com/join/{token}"
        # Join links are for the people who manage the team.
        assert team["staff"][1].get("/api/team/").json()["invites"] == []

    def test_invite_emails_a_join_link(self, team, owner_a):
        _, c = team["admin"]
        res = c.post(
            "/api/team/invites/", {"email": "bupe@example.com", "role": "accountant"}, format="json"
        )
        assert res.status_code == 201
        inv = Invite.objects.get(email="bupe@example.com")
        assert mail.outbox[-1].to == ["bupe@example.com"]
        assert f"https://app.example.com/join/{inv.token}" in mail.outbox[-1].body
        assert owner_a.business.name in mail.outbox[-1].subject

    def test_reinvite_replaces_open_invite(self, team):
        _, c = team["owner"]
        for role in ("staff", "accountant"):
            c.post("/api/team/invites/", {"email": "a@example.com", "role": role}, format="json")
        assert list(
            Invite.objects.filter(email="a@example.com").values_list("role", flat=True)
        ) == ["accountant"]

    def test_cannot_invite_existing_member(self, team):
        staff, _ = team["staff"]
        _, c = team["owner"]
        res = c.post(
            "/api/team/invites/",
            {"email": staff.user.email.upper(), "role": "staff"},
            format="json",
        )
        assert res.status_code == 400

    def test_admin_cannot_create_or_change_owners(self, team):
        _, c = team["admin"]
        owner, _ = team["owner"]
        staff, _ = team["staff"]
        assert (
            c.post("/api/team/invites/", {"email": "o@example.com", "role": "owner"}).status_code
            == 403
        )
        assert c.patch(f"/api/team/members/{staff.id}/", {"role": "owner"}).status_code == 403
        assert c.patch(f"/api/team/members/{owner.id}/", {"role": "staff"}).status_code == 403
        assert c.delete(f"/api/team/members/{owner.id}/").status_code == 403
        assert c.patch(f"/api/team/members/{staff.id}/", {"role": "accountant"}).status_code == 200
        staff.refresh_from_db()
        assert staff.role == "accountant"

    def test_owner_can_promote_and_remove(self, team):
        _, c = team["owner"]
        staff, _ = team["staff"]
        admin, _ = team["admin"]
        assert c.patch(f"/api/team/members/{staff.id}/", {"role": "owner"}).status_code == 200
        assert c.delete(f"/api/team/members/{admin.id}/").status_code == 200
        assert not Membership.objects.filter(pk=admin.pk).exists()

    def test_last_owner_is_protected(self, team):
        owner, c = team["owner"]
        res = c.patch(f"/api/team/members/{owner.id}/", {"role": "admin"})
        assert res.status_code == 400
        assert "needs an owner" in res.json()["detail"]
        assert c.delete(f"/api/team/members/{owner.id}/").status_code == 400

    def test_member_can_leave(self, team, owner_a):
        staff, c = team["staff"]
        assert c.delete(f"/api/team/members/{staff.id}/").status_code == 200
        assert not Membership.objects.filter(pk=staff.pk).exists()
        assert c.get("/api/customers/").status_code == 403

    def test_revoke_invite(self, team):
        _, c = team["owner"]
        c.post("/api/team/invites/", {"email": "a@example.com", "role": "staff"})
        inv = Invite.objects.get()
        assert team["staff"][1].delete(f"/api/team/invites/{inv.id}/").status_code == 403
        assert c.delete(f"/api/team/invites/{inv.id}/").json()["invites"] == []
        assert c.delete(f"/api/team/invites/{inv.id}/").status_code == 404

    def test_other_business_members_are_invisible(self, team, owner_b):
        _, c = team["owner"]
        assert c.patch(f"/api/team/members/{owner_b.id}/", {"role": "staff"}).status_code == 404
        assert c.delete(f"/api/team/members/{owner_b.id}/").status_code == 404
        other = Invite.objects.create(
            business=owner_b.business, email="z@example.com", role="staff"
        )
        assert c.delete(f"/api/team/invites/{other.id}/").status_code == 404


class TestJoining:
    @pytest.fixture
    def invite(self, owner_a):
        return Invite.objects.create(
            business=owner_a.business,
            email="chanda@example.com",
            role="staff",
            invited_by=owner_a.user,
        )

    def test_invite_info_is_public(self, api_client, invite, owner_a):
        data = api_client.get(f"/api/auth/invites/{invite.token}/").json()
        assert data["business"] == owner_a.business.name
        assert data["email"] == "chanda@example.com"
        assert data["is_open"] is True

    def test_unknown_token_is_404(self, api_client):
        assert (
            api_client.get("/api/auth/invites/00000000-0000-0000-0000-000000000000/").status_code
            == 404
        )

    def test_accept_joins_and_switches_business(self, invite, owner_a):
        user = UserFactory(email="Chanda@example.com")
        MembershipFactory(user=user)  # already runs their own business
        c = login_as(user)
        assert c.post(f"/api/auth/invites/{invite.token}/accept/").status_code == 204
        assert Membership.objects.get(user=user, business=owner_a.business).role == "staff"
        assert c.session[SESSION_KEY] == owner_a.business.id
        assert c.get("/api/auth/me/").json()["current_business"]["id"] == owner_a.business.id
        invite.refresh_from_db()
        assert invite.accepted_at is not None
        assert c.post(f"/api/auth/invites/{invite.token}/accept/").status_code == 400

    def test_accept_needs_matching_email(self, invite):
        c = login_as(UserFactory(email="someone@example.com"))
        res = c.post(f"/api/auth/invites/{invite.token}/accept/")
        assert res.status_code == 403
        assert "chanda@example.com" in res.json()["detail"]

    def test_accept_needs_login(self, api_client, invite):
        assert api_client.post(f"/api/auth/invites/{invite.token}/accept/").status_code == 403

    def test_expired_invite(self, invite):
        Invite.objects.filter(pk=invite.pk).update(
            expires_at=timezone.now() - dt.timedelta(minutes=1)
        )
        c = login_as(UserFactory(email="chanda@example.com"))
        assert c.post(f"/api/auth/invites/{invite.token}/accept/").status_code == 400
