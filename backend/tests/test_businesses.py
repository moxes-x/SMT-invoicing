import pytest

from apps.accounts.models import Membership

from .factories import MembershipFactory


@pytest.mark.django_db
class TestBusinessOnboarding:
    def test_create_business_makes_user_owner_and_current(self, api_client):
        user = MembershipFactory.build().user
        user.save()
        api_client.force_login(user)
        res = api_client.post(
            "/api/businesses/",
            {"name": "Chanda Salon", "phone": "0971234567", "vat_registered": False},
            format="json",
        )
        assert res.status_code == 201, res.content
        body = res.json()
        assert body["phone"] == "+260971234567"  # normalised to E.164
        assert body["role"] == "owner"
        assert body["compliance_notice"] is None
        me = api_client.get("/api/auth/me/").json()
        assert me["current_business"]["id"] == body["id"]

    def test_vat_registered_business_gets_smart_invoice_notice(self, client_a):
        res = client_a.post(
            "/api/businesses/", {"name": "Big Co", "vat_registered": True}, format="json"
        )
        assert res.status_code == 201
        assert "Smart Invoice" in res.json()["compliance_notice"]

    def test_invalid_phone_and_tpin_rejected(self, client_a):
        res = client_a.post(
            "/api/businesses/", {"name": "X", "phone": "12", "tpin": "abc"}, format="json"
        )
        assert res.status_code == 400
        assert set(res.json()) >= {"phone", "tpin"}

    def test_member_role_cannot_edit_business(self, api_client, owner_a):
        member = MembershipFactory(business=owner_a.business, role=Membership.Role.MEMBER)
        api_client.force_login(member.user)
        res = api_client.patch(
            f"/api/businesses/{owner_a.business.id}/", {"name": "Hijacked"}, format="json"
        )
        assert res.status_code == 403

    def test_switch_current_business(self, client_a, owner_a):
        second = MembershipFactory(user=owner_a.user).business
        res = client_a.post(f"/api/businesses/{second.id}/switch/")
        assert res.status_code == 200
        assert res.json()["current_business"]["id"] == second.id


@pytest.mark.django_db
class TestTenantIsolation:
    """A user from Business A must get 404 on every Business B endpoint."""

    def test_list_only_shows_own_businesses(self, client_a, owner_a, owner_b):
        ids = [b["id"] for b in client_a.get("/api/businesses/").json()["results"]]
        assert ids == [owner_a.business.id]

    @pytest.mark.parametrize(
        ("method", "suffix"),
        [("get", ""), ("patch", ""), ("put", ""), ("post", "switch/")],
    )
    def test_other_business_returns_404(self, client_a, owner_b, method, suffix):
        url = f"/api/businesses/{owner_b.business.id}/{suffix}"
        res = getattr(client_a, method)(url, {"name": "pwned"}, format="json")
        assert res.status_code == 404
        owner_b.business.refresh_from_db()
        assert owner_b.business.name != "pwned"

    def test_stale_session_business_falls_back_to_own(self, client_a, owner_a, owner_b):
        session = client_a.session
        session["current_business_id"] = owner_b.business.id  # forged / stale
        session.save()
        me = client_a.get("/api/auth/me/").json()
        assert me["current_business"]["id"] == owner_a.business.id
