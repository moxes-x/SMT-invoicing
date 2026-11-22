import datetime as dt
from decimal import Decimal

import pytest

from apps.core.money import format_rate, to_kwacha
from apps.invoices.services import record_payment, void_invoice

from .factories import CustomerFactory, MembershipFactory, make_invoice

pytestmark = pytest.mark.django_db


def line(price: int) -> list[dict]:
    return [{"description": "Work", "quantity": Decimal("1"), "unit_price": price}]


@pytest.fixture
def books(owner_a, time_machine):
    """Nov 2026: K1,000 + $100 (rate 25) + $50 (no rate) invoiced; some paid; one void."""
    time_machine.move_to("2026-11-20T10:00:00+02:00")
    b, u = owner_a.business, owner_a.user
    acme = CustomerFactory(business=b, name="Acme")
    zmw = make_invoice(
        b, user=u, send=True, customer=acme, lines=line(100_000),
        issue_date=dt.date(2026, 11, 2), due_date=dt.date(2026, 11, 10),
    )  # fmt: skip
    usd = make_invoice(
        b, user=u, send=True, currency="USD", exchange_rate=Decimal("25"), lines=line(10_000),
        issue_date=dt.date(2026, 11, 3), due_date=dt.date(2026, 12, 3),
    )  # fmt: skip
    make_invoice(
        b, user=u, send=True, currency="USD", lines=line(5_000),
        issue_date=dt.date(2026, 11, 4), due_date=dt.date(2026, 12, 4),
    )  # fmt: skip
    gone = make_invoice(b, user=u, send=True, lines=line(999_00), issue_date=dt.date(2026, 11, 5))
    void_invoice(gone, u, "mistake")
    make_invoice(b, user=u, lines=line(777_00), issue_date=dt.date(2026, 11, 6))  # draft
    # October invoice paid in November: counts as collected, not invoiced
    old = make_invoice(
        b, user=u, send=True, lines=line(20_000),
        issue_date=dt.date(2026, 10, 1), due_date=dt.date(2026, 10, 15),
    )  # fmt: skip
    record_payment(old, u, amount=20_000, method="cash", paid_on=dt.date(2026, 11, 1))
    record_payment(zmw, u, amount=40_000, method="mtn_momo", paid_on=dt.date(2026, 11, 12))
    record_payment(usd, u, amount=4_000, method="bank", paid_on=dt.date(2026, 11, 15))
    return {"zmw": zmw, "usd": usd}


def get(client, **params):
    res = client.get("/api/reports/", params)
    assert res.status_code == 200, res.content
    return res.json()


class TestReport:
    def test_per_currency_figures(self, client_a, books):
        data = get(client_a, start="2026-11-01", end="2026-11-30")
        assert [c["currency"] for c in data["currencies"]] == ["ZMW", "USD"]
        zmw, usd = data["currencies"]
        # Void and draft left out; October invoice not invoiced this month
        assert zmw["invoiced"] == {"amount": 100_000, "count": 1}
        assert zmw["collected"] == {"amount": 60_000, "count": 2}
        assert {m["method"]: m["amount"] for m in zmw["by_method"]} == {
            "mtn_momo": 40_000,
            "cash": 20_000,
        }
        assert usd["invoiced"] == {"amount": 15_000, "count": 2}
        assert usd["collected"] == {"amount": 4_000, "count": 1}
        # Owed now: ZMW 600 overdue (due 10 Nov); USD 60 + 50 not due yet
        assert zmw["outstanding"] == {"amount": 60_000, "count": 1}
        assert zmw["overdue"] == {"amount": 60_000, "count": 1}
        assert usd["outstanding"] == {"amount": 11_000, "count": 2}
        assert usd["overdue"]["amount"] == 0
        aging = {a["bucket"]: a["amount"] for a in zmw["aging"]}
        assert aging["1_30"] == 60_000 and aging["not_due"] == 0
        assert {a["bucket"]: a["amount"] for a in usd["aging"]}["not_due"] == 11_000
        assert zmw["top_customers"][0]["name"] == "Acme"

    def test_kwacha_uses_each_invoices_rate_and_counts_missing(self, client_a, books):
        kw = get(client_a, start="2026-11-01", end="2026-11-30")["kwacha"]
        # K1,000 + $100 x 25; the $50 invoice has no rate
        assert kw["invoiced"] == 100_000 + 250_000
        assert kw["collected"] == 60_000 + 100_000
        assert kw["outstanding"] == 60_000 + 150_000
        assert kw["missing_rates"] == 1
        assert kw["months"] == [{"month": "2026-11", "invoiced": 350_000, "collected": 160_000}]

    def test_months_cover_the_range(self, client_a, books):
        data = get(client_a, start="2026-10-01", end="2026-11-30")
        zmw = data["currencies"][0]
        assert zmw["months"] == [
            {"month": "2026-10", "invoiced": 20_000, "collected": 0},
            {"month": "2026-11", "invoiced": 100_000, "collected": 60_000},
        ]

    def test_defaults_to_this_month(self, client_a, books):
        data = get(client_a)
        assert (data["start"], data["end"]) == ("2026-11-01", "2026-11-20")

    def test_bad_ranges(self, client_a):
        assert client_a.get("/api/reports/?start=2026-12-01&end=2026-11-01").status_code == 400
        assert client_a.get("/api/reports/?start=2020-01-01&end=2026-11-01").status_code == 400
        assert client_a.get("/api/reports/?start=nope").status_code == 400

    def test_empty_business_gets_default_currency(self, client_a):
        data = get(client_a)
        assert [c["currency"] for c in data["currencies"]] == ["ZMW"]
        assert data["kwacha"]["missing_rates"] == 0

    def test_other_business_figures_not_included(self, books, owner_b):
        from rest_framework.test import APIClient

        c = APIClient()
        c.force_login(owner_b.user)
        data = get(c, start="2026-11-01", end="2026-11-30")
        assert data["currencies"][0]["invoiced"]["amount"] == 0

    def test_accountant_can_read(self, owner_a, books):
        from rest_framework.test import APIClient

        acc = MembershipFactory(business=owner_a.business, role="accountant")
        c = APIClient()
        c.force_login(acc.user)
        assert c.get("/api/reports/").status_code == 200
        assert c.get("/api/reports/export/").status_code == 200

    def test_csv(self, client_a, books):
        res = client_a.get("/api/reports/export/?start=2026-11-01&end=2026-11-30")
        text = res.content.decode("utf-8-sig")
        assert res["Content-Type"].startswith("text/csv")
        assert "Month,Currency,Invoiced,Collected" in text
        assert "2026-11,ZMW,1000.00,600.00" in text
        assert "2026-11,USD,150.00,40.00" in text
        assert "2026-11,ZMW equivalent,3500.00,1600.00" in text


class TestExchangeRate:
    def test_editor_saves_rate_and_zmw_drops_it(self, client_a, owner_a):
        customer = CustomerFactory(business=owner_a.business)
        body = {
            "customer_id": customer.id,
            "currency": "USD",
            "exchange_rate": "26.85",
            "issue_date": "2026-11-01",
            "due_date": "2026-11-15",
            "lines": [{"description": "x", "quantity": "1", "unit_price": 1000}],
        }
        res = client_a.post("/api/invoices/", body, format="json")
        assert res.status_code == 201, res.content
        assert res.json()["exchange_rate"] == "26.8500"
        body |= {"currency": "ZMW"}
        assert client_a.post("/api/invoices/", body, format="json").json()["exchange_rate"] is None
        body |= {"currency": "USD", "exchange_rate": "0"}
        assert client_a.post("/api/invoices/", body, format="json").status_code == 400

    def test_set_rate_after_sending(self, client_a, owner_a):
        inv = make_invoice(owner_a.business, send=True, currency="USD")
        res = client_a.post(
            f"/api/invoices/{inv.id}/exchange-rate/", {"exchange_rate": "27.5"}, format="json"
        )
        assert res.status_code == 200
        assert res.json()["exchange_rate"] == "27.5000"
        assert "1 USD = K27.50" in res.json()["activity"][0]["message"]

    def test_rate_rules(self, client_a, owner_a):
        zmw = make_invoice(owner_a.business, send=True)
        url = f"/api/invoices/{zmw.id}/exchange-rate/"
        assert client_a.post(url, {"exchange_rate": "2"}, format="json").status_code == 400
        usd = make_invoice(owner_a.business, send=True, currency="USD")
        url = f"/api/invoices/{usd.id}/exchange-rate/"
        assert client_a.post(url, {"exchange_rate": "-1"}, format="json").status_code == 400

    def test_reissue_keeps_rate(self, client_a, owner_a):
        inv = make_invoice(owner_a.business, send=True, currency="USD", exchange_rate=Decimal("26"))
        res = client_a.post(f"/api/invoices/{inv.id}/reissue/", {}, format="json")
        assert res.json()["exchange_rate"] == "26.0000"

    def test_pdf_shows_kwacha_total(self, owner_a):
        from django.template.loader import render_to_string

        from apps.invoices.pdf import document_context

        inv = make_invoice(
            owner_a.business, send=True, currency="USD", exchange_rate=Decimal("26.5")
        )
        html = render_to_string(inv.DOCUMENT_TEMPLATE, document_context(inv))
        assert "Total in Kwacha at K26.50 = 1 USD" in html
        assert "K13,250.00" in html  # $500 x 26.5


def test_money_helpers():
    assert to_kwacha(100, "ZMW", None) == 100
    assert to_kwacha(100, "USD", None) is None
    assert to_kwacha(333, "USD", Decimal("26.8513")) == 8941  # 8941.4829 → 8941
    assert format_rate(Decimal("27.5000")) == "27.50"
    assert format_rate(Decimal("26.8513")) == "26.8513"
    assert format_rate(Decimal("1234.1")) == "1,234.10"
