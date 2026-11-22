import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from .factories import MembershipFactory


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def owner_a():
    return MembershipFactory()


@pytest.fixture
def owner_b():
    return MembershipFactory()


@pytest.fixture
def client_a(owner_a) -> APIClient:
    client = APIClient()
    client.force_login(owner_a.user)
    return client


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()  # throttling counters live in the cache
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _settings(settings, tmp_path):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.PUBLIC_BASE_URL = "https://app.example.com"


@pytest.fixture
def time_machine():
    """Freeze/move time: time_machine.move_to("2026-11-15T22:00:00Z")."""
    import time_machine as tm

    class Mover:
        traveller = None

        def move_to(self, when):
            if self.traveller is not None:
                self.traveller.stop()
            self.traveller = tm.travel(when, tick=False)
            self.traveller.start()

    mover = Mover()
    yield mover
    if mover.traveller is not None:
        mover.traveller.stop()


class FakeMeta:
    """Stands in for graph.facebook.com. Records requests; fail_with makes the next send fail."""

    def __init__(self):
        self.requests = []
        self.fail_with = None  # (status_code, error_code)
        self.counter = 0

    def handler(self, request):
        import httpx

        self.requests.append(request)
        if request.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "media-1"})
        if self.fail_with:
            status, code = self.fail_with
            return httpx.Response(status, json={"error": {"message": "boom", "code": code}})
        self.counter += 1
        return httpx.Response(200, json={"messages": [{"id": f"wamid.{self.counter}"}]})

    def sent_payloads(self):
        import json

        return [json.loads(r.content) for r in self.requests if r.url.path.endswith("/messages")]


@pytest.fixture
def whatsapp_api(settings, monkeypatch):
    import httpx

    settings.WHATSAPP_TOKEN = "test-token"
    settings.WHATSAPP_PHONE_NUMBER_ID = "123456"
    settings.WHATSAPP_APP_SECRET = "app-secret"
    settings.WHATSAPP_VERIFY_TOKEN = "verify-me"
    fake = FakeMeta()
    real_client = httpx.Client
    monkeypatch.setattr(
        "apps.messaging.whatsapp.httpx.Client",
        lambda **kw: real_client(transport=httpx.MockTransport(fake.handler)),
    )
    return fake
