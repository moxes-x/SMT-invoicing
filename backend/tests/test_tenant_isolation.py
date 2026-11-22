"""A user from Business A must get 404 on every Business B object endpoint."""

import pytest

from .factories import CustomerFactory, ItemFactory, make_invoice


@pytest.fixture
def b_objects(owner_b):
    biz = owner_b.business
    invoice = make_invoice(biz, send=True)
    from apps.invoices.services import record_payment

    payment = record_payment(invoice, None, amount=100, method="cash")
    return {
        "customer": CustomerFactory(business=biz),
        "item": ItemFactory(business=biz),
        "invoice": invoice,
        "draft": make_invoice(biz),
        "payment": payment,
    }


ENDPOINTS = [
    ("get", "/api/customers/{customer.id}/"),
    ("patch", "/api/customers/{customer.id}/"),
    ("delete", "/api/customers/{customer.id}/"),
    ("get", "/api/items/{item.id}/"),
    ("patch", "/api/items/{item.id}/"),
    ("delete", "/api/items/{item.id}/"),
    ("get", "/api/invoices/{invoice.id}/"),
    ("patch", "/api/invoices/{draft.id}/"),
    ("post", "/api/invoices/{draft.id}/send/"),
    ("post", "/api/invoices/{invoice.id}/void/"),
    ("post", "/api/invoices/{invoice.id}/reissue/"),
    ("post", "/api/invoices/{invoice.id}/payments/"),
    ("post", "/api/invoices/{invoice.id}/whatsapp/"),
    ("post", "/api/invoices/{invoice.id}/email/"),
    ("get", "/api/invoices/{invoice.id}/pdf/"),
    ("get", "/api/payments/{payment.id}/"),
    ("delete", "/api/payments/{payment.id}/"),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("method", "template"), ENDPOINTS)
def test_other_business_objects_are_404(client_a, b_objects, method, template):
    url = template.format(**b_objects)
    res = getattr(client_a, method)(
        url, {"amount": 1, "method": "cash", "name": "x"}, format="json"
    )
    assert res.status_code == 404, (url, res.status_code)


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["customers", "items", "invoices", "payments"])
def test_lists_never_include_other_business(client_a, owner_a, b_objects, path):
    assert client_a.get(f"/api/{path}/").json()["count"] == 0


@pytest.mark.django_db
def test_cannot_invoice_another_business_customer(client_a, b_objects):
    res = client_a.post(
        "/api/invoices/",
        {
            "customer_id": b_objects["customer"].id,
            "due_date": "2026-12-01",
            "lines": [{"description": "x", "quantity": "1", "unit_price": 100}],
        },
        format="json",
    )
    assert res.status_code == 400
    assert "customer_id" in res.json()


@pytest.mark.django_db
def test_dashboard_only_counts_own_business(client_a, b_objects):
    data = client_a.get("/api/dashboard/").json()
    assert data["owed"] == [] and data["top_debtors"] == [] and data["recent"] == []


@pytest.mark.django_db
def test_user_without_business_is_forbidden(api_client):
    from .factories import UserFactory

    api_client.force_login(UserFactory())
    assert api_client.get("/api/invoices/").status_code == 403
