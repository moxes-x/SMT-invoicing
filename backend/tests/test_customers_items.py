import pytest

from .factories import CustomerFactory, ItemFactory, make_invoice


@pytest.mark.django_db
class TestCustomers:
    def test_create_normalises_phone(self, client_a, owner_a):
        res = client_a.post(
            "/api/customers/", {"name": "Chileshe", "phone": "0977 123 456"}, format="json"
        )
        assert res.status_code == 201, res.content
        assert res.json()["phone"] == "+260977123456"

    def test_rejects_bad_phone(self, client_a):
        res = client_a.post("/api/customers/", {"name": "X", "phone": "123"}, format="json")
        assert res.status_code == 400

    def test_search(self, client_a, owner_a):
        CustomerFactory(business=owner_a.business, name="Mutale Phiri")
        CustomerFactory(business=owner_a.business, name="Bupe Zulu")
        names = [c["name"] for c in client_a.get("/api/customers/?search=mutale").json()["results"]]
        assert names == ["Mutale Phiri"]

    def test_cannot_delete_customer_with_invoices(self, client_a, owner_a):
        inv = make_invoice(owner_a.business)
        res = client_a.delete(f"/api/customers/{inv.customer_id}/")
        assert res.status_code == 409


@pytest.mark.django_db
def test_items_crud(client_a, owner_a):
    res = client_a.post("/api/items/", {"name": "Braids", "unit_price": 35000}, format="json")
    assert res.status_code == 201
    item_id = res.json()["id"]
    assert (
        client_a.patch(f"/api/items/{item_id}/", {"unit_price": 40000}, format="json").json()[
            "unit_price"
        ]
        == 40000
    )
    assert (
        client_a.post("/api/items/", {"name": "x", "unit_price": -1}, format="json").status_code
        == 400
    )
    ItemFactory(business=owner_a.business)
    assert client_a.get("/api/items/").json()["count"] == 2
