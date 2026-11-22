import pytest
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
