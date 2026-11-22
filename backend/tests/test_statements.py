import datetime as dt

import pytest

from apps.invoices.services import record_payment, void_invoice

from .factories import CustomerFactory, make_invoice


@pytest.fixture
def history(owner_a):
    """Oct: INV 500 (paid 200 in Oct). Nov: INV 300, payment 300 on the Oct one. Plus noise."""
    b = owner_a.business
    customer = CustomerFactory(business=b, name="Chanda Mwale")
    oct_inv = make_invoice(
        b,
        customer=customer,
        send=True,
        issue_date=dt.date(2026, 10, 5),
        due_date=dt.date(2026, 10, 20),
    )
    record_payment(oct_inv, None, amount=20000, method="cash", paid_on=dt.date(2026, 10, 10))
    nov_inv = make_invoice(
        b,
        customer=customer,
        send=True,
        issue_date=dt.date(2026, 11, 3),
        due_date=dt.date(2026, 11, 30),
        lines=[{"description": "Repairs", "quantity": 1, "unit_price": 30000}],
    )
    record_payment(oct_inv, None, amount=30000, method="mtn_momo", paid_on=dt.date(2026, 11, 4))
    # Not on the statement: a draft, a void invoice, another currency, another customer
    make_invoice(b, customer=customer, issue_date=dt.date(2026, 11, 5))
    void_invoice(
        make_invoice(b, customer=customer, send=True, issue_date=dt.date(2026, 11, 6)), None
    )
    make_invoice(b, customer=customer, send=True, currency="USD", issue_date=dt.date(2026, 11, 7))
    make_invoice(b, send=True, issue_date=dt.date(2026, 11, 8))
    return customer, oct_inv, nov_inv


@pytest.mark.django_db
class TestStatement:
    def test_running_balance(self, client_a, history):
        customer, oct_inv, nov_inv = history
        res = client_a.get(
            f"/api/customers/{customer.id}/statement/",
            {"start": "2026-11-01", "end": "2026-11-30", "currency": "ZMW"},
        )
        assert res.status_code == 200, res.content
        body = res.json()
        assert body["opening"] == 50000 - 20000
        assert [(r["kind"], r["debit"], r["credit"], r["balance"]) for r in body["rows"]] == [
            ("invoice", 30000, 0, 60000),
            ("payment", 0, 30000, 30000),
        ]
        assert (body["invoiced"], body["paid"], body["closing"]) == (30000, 30000, 30000)
        assert body["rows"][1]["reference"].startswith("RCT-")

    def test_whole_history_and_pdf(self, client_a, history):
        customer, *_ = history
        res = client_a.get(
            f"/api/customers/{customer.id}/statement/", {"start": "2026-01-01", "end": "2026-12-31"}
        )
        body = res.json()
        assert body["opening"] == 0 and body["closing"] == 30000 and len(body["rows"]) == 4
        pdf = client_a.get(
            f"/api/customers/{customer.id}/statement/pdf/",
            {"start": "2026-01-01", "end": "2026-12-31"},
        )
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        assert "statement-chanda-mwale-2026-12-31.pdf" in pdf["Content-Disposition"]

    def test_validation_and_isolation(self, client_a, owner_b, history):
        customer, *_ = history
        url = f"/api/customers/{customer.id}/statement/"
        assert client_a.get(url, {"start": "2026-12-01", "end": "2026-11-01"}).status_code == 400
        assert client_a.get(url, {"start": "soon"}).status_code == 400
        assert client_a.get(url, {"currency": "EUR"}).status_code == 400
        other = CustomerFactory(business=owner_b.business)
        assert client_a.get(f"/api/customers/{other.id}/statement/").status_code == 404
        assert client_a.get(f"/api/customers/{other.id}/statement/pdf/").status_code == 404


@pytest.mark.django_db
class TestExports:
    def test_invoices_csv(self, client_a, owner_b, history):
        make_invoice(owner_b.business, send=True)  # other tenant
        res = client_a.get("/api/invoices/export/", {"status": "unpaid"})
        assert res.status_code == 200
        assert res["Content-Type"].startswith("text/csv")
        lines = res.content.decode("utf-8-sig").strip().splitlines()
        assert lines[0] == "Number,Issued,Due,Customer,Currency,Total,Paid,Balance,Status"
        assert len(lines) == 1 + 3  # Nov ZMW, USD, the other customer's; Oct is paid
        assert any(",Chanda Mwale,ZMW,300.00,0.00,300.00," in line for line in lines)

    def test_payments_csv(self, client_a, owner_b, history):
        res = client_a.get("/api/payments/export/", {"start": "2026-11-01"})
        lines = res.content.decode("utf-8-sig").strip().splitlines()
        assert lines[0].startswith("Date,Receipt,Invoice,Customer")
        assert len(lines) == 2
        assert lines[1].startswith("2026-11-04,RCT-2026-0002,") and ",300.00,MTN MoMo," in lines[1]
        assert client_a.get("/api/payments/export/", {"end": "nope"}).status_code == 400
