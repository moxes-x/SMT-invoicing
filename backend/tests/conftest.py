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
