import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User

PASSWORD = "correct-horse-battery"


def csrf_client() -> APIClient:
    """A client that enforces CSRF exactly like a browser would."""
    client = APIClient(enforce_csrf_checks=True)
    res = client.get("/api/auth/csrf/")
    assert res.status_code == 204
    client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    return client


@pytest.mark.django_db
class TestSignupLogin:
    def test_signup_logs_in_and_lowercases_email(self):
        client = csrf_client()
        res = client.post(
            "/api/auth/signup/",
            {"email": "Mwila@Example.com", "password": PASSWORD, "full_name": "Mwila"},
            format="json",
        )
        assert res.status_code == 201, res.content
        body = res.json()
        assert body["user"]["email"] == "mwila@example.com"
        assert body["current_business"] is None
        assert client.get("/api/auth/me/").status_code == 200

    def test_signup_rejects_duplicate_email_case_insensitive(self):
        User.objects.create_user("taken@example.com", PASSWORD)
        res = csrf_client().post(
            "/api/auth/signup/", {"email": "TAKEN@example.com", "password": PASSWORD}, format="json"
        )
        assert res.status_code == 400

    def test_signup_rejects_weak_password(self):
        res = csrf_client().post(
            "/api/auth/signup/", {"email": "a@example.com", "password": "12345678"}, format="json"
        )
        assert res.status_code == 400

    def test_login_and_logout(self):
        User.objects.create_user("bwalya@example.com", PASSWORD)
        client = csrf_client()
        res = client.post(
            "/api/auth/login/", {"email": "BWALYA@example.com", "password": PASSWORD}, format="json"
        )
        assert res.status_code == 200, res.content
        assert client.get("/api/auth/me/").status_code == 200
        # login rotates the CSRF token; pick up the new one
        client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        assert client.post("/api/auth/logout/").status_code == 204
        assert client.get("/api/auth/me/").status_code == 403

    def test_wrong_password_rejected(self):
        User.objects.create_user("bwalya@example.com", PASSWORD)
        res = csrf_client().post(
            "/api/auth/login/", {"email": "bwalya@example.com", "password": "nope"}, format="json"
        )
        assert res.status_code == 400

    def test_post_without_csrf_token_is_rejected(self):
        client = APIClient(enforce_csrf_checks=True)
        client.get("/api/auth/csrf/")
        res = client.post(
            "/api/auth/signup/", {"email": "x@example.com", "password": PASSWORD}, format="json"
        )
        assert res.status_code == 403

    def test_me_requires_login(self, api_client):
        assert api_client.get("/api/auth/me/").status_code == 403
