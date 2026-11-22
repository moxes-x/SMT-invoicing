import pytest


@pytest.mark.django_db
def test_health_is_public(api_client):
    res = api_client.get("/api/health/")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "database": "ok"}


@pytest.mark.django_db
def test_openapi_schema_builds(api_client, owner_a):
    api_client.force_login(owner_a.user)
    res = api_client.get("/api/schema/")
    assert res.status_code == 200
