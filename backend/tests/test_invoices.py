import datetime as dt
from decimal import Decimal

import pytest
from django.core import mail

from apps.audit.models import ActivityLog
from apps.invoices.models import Invoice
from apps.messaging.models import Delivery

from .factories import CustomerFactory, ItemFactory, make_invoice


def payload(customer_id, **extra):
    data = {
        "customer_id": customer_id,
        "issue_date": "2026-11-01",
        "due_date": "2026-11-15",
        "notes": "Thank you",
        "lines": [
            {"description": "Haircut", "quantity": "2", "unit_price": 12500, "discount": 1000},
            {"description": "Treatment", "quantity": "1.5", "unit_price": 10000},
        ],
    }
    data.update(extra)
    return data


@pytest.mark.django_db
class TestCreateAndEdit:
    def test_totals_are_computed_server_side(self, client_a, owner_a):
        customer = CustomerFactory(business=owner_a.business)
        res = client_a.post(
            "/api/invoices/", payload(customer.id, total=1, subtotal=1), format="json"
        )
        assert res.status_code == 201, res.content
        body = res.json()
        assert (body["subtotal"], body["discount_total"], body["total"]) == (40000, 1000, 39000)
        assert body["number"] == "INV-2026-0001"
        assert body["status"] == "draft"
        assert [line["amount"] for line in body["lines"]] == [24000, 15000]

    @pytest.mark.parametrize(
        "line",
        [
            {"description": "x", "quantity": "0", "unit_price": 100},
            {"description": "x", "quantity": "-1", "unit_price": 100},
            {"description": "x", "quantity": "1", "unit_price": 0},
            {"description": "x", "quantity": "1", "unit_price": -100},
            {"description": "x", "quantity": "1", "unit_price": 100, "discount": 101},
        ],
    )
    def test_rejects_zero_and_negative(self, client_a, owner_a, line):
        customer = CustomerFactory(business=owner_a.business)
        res = client_a.post("/api/invoices/", payload(customer.id, lines=[line]), format="json")
        assert res.status_code == 400

    def test_due_date_before_issue_rejected(self, client_a, owner_a):
        customer = CustomerFactory(business=owner_a.business)
        res = client_a.post(
            "/api/invoices/", payload(customer.id, due_date="2026-10-01"), format="json"
        )
        assert res.status_code == 400

    def test_draft_can_be_edited_and_lines_replaced(self, client_a, owner_a):
        inv = make_invoice(owner_a.business)
        res = client_a.patch(
            f"/api/invoices/{inv.id}/",
            {"lines": [{"description": "Wash", "quantity": "3", "unit_price": 2000}]},
            format="json",
        )
        assert res.status_code == 200, res.content
        assert res.json()["total"] == 6000
        assert len(res.json()["lines"]) == 1

    def test_line_item_must_belong_to_business(self, client_a, owner_a, owner_b):
        foreign_item = ItemFactory(business=owner_b.business)
        customer = CustomerFactory(business=owner_a.business)
        line = {"item": foreign_item.id, "description": "x", "quantity": "1", "unit_price": 100}
        res = client_a.post("/api/invoices/", payload(customer.id, lines=[line]), format="json")
        assert res.status_code == 400


@pytest.mark.django_db
class TestLifecycle:
    def test_sent_invoice_is_locked(self, client_a, owner_a):
        inv = make_invoice(owner_a.business, send=True)
        res = client_a.patch(f"/api/invoices/{inv.id}/", {"notes": "changed"}, format="json")
        assert res.status_code == 400
        inv.refresh_from_db()
        assert inv.notes == ""

    def test_cannot_send_empty_draft(self, client_a, owner_a):
        inv = make_invoice(owner_a.business)
        inv.lines.all().delete()
        assert client_a.post(f"/api/invoices/{inv.id}/send/").status_code == 400

    def test_void_and_reissue(self, client_a, owner_a):
        inv = make_invoice(owner_a.business, send=True)
        res = client_a.post(f"/api/invoices/{inv.id}/reissue/", {"reason": "Wrong price"})
        assert res.status_code == 201, res.content
        copy = res.json()
        assert copy["status"] == "draft"
        assert copy["number"] == "INV-2026-0002"
        assert copy["reissued_from"]["number"] == inv.number
        assert copy["total"] == inv.total
        original = client_a.get(f"/api/invoices/{inv.id}/").json()
        assert original["status"] == "void"
        assert original["reissued_as"]["id"] == copy["id"]
        assert client_a.post(f"/api/invoices/{inv.id}/reissue/").status_code == 400

    def test_cannot_void_invoice_with_payments(self, client_a, owner_a):
        inv = make_invoice(owner_a.business, send=True)
        client_a.post(f"/api/invoices/{inv.id}/payments/", {"amount": 100, "method": "cash"})
        assert client_a.post(f"/api/invoices/{inv.id}/void/").status_code == 400

    def test_invoices_cannot_be_deleted(self, client_a, owner_a):
        inv = make_invoice(owner_a.business)
        assert client_a.delete(f"/api/invoices/{inv.id}/").status_code == 405


@pytest.mark.django_db
class TestPaymentsAndStatus:
    def test_unpaid_partial_paid(self, client_a, owner_a):
        inv = make_invoice(owner_a.business, send=True)  # K500.00
        url = f"/api/invoices/{inv.id}/"
        assert client_a.get(url).json()["payment_status"] == "unpaid"

        res = client_a.post(
            url + "payments/",
            {"amount": 20000, "method": "mtn_momo", "reference": "MP123"},
            format="json",
        )
        assert res.status_code == 201, res.content
        body = client_a.get(url).json()
        assert (body["payment_status"], body["balance"]) == ("partial", 30000)

        client_a.post(url + "payments/", {"amount": 30000, "method": "cash"}, format="json")
        body = client_a.get(url).json()
        assert (body["payment_status"], body["display_status"], body["balance"]) == (
            "paid",
            "paid",
            0,
        )
        verbs = [a["verb"] for a in body["activity"]]
        assert verbs.count("payment_recorded") == 2

    def test_overpayment_rejected(self, client_a, owner_a):
        inv = make_invoice(owner_a.business, send=True)
        res = client_a.post(
            f"/api/invoices/{inv.id}/payments/", {"amount": 50001, "method": "cash"}, format="json"
        )
        assert res.status_code == 400
        assert "K500.00" in res.json()["amount"][0]

    @pytest.mark.parametrize("amount", [0, -100])
    def test_non_positive_payment_rejected(self, client_a, owner_a, amount):
        inv = make_invoice(owner_a.business, send=True)
        res = client_a.post(
            f"/api/invoices/{inv.id}/payments/", {"amount": amount, "method": "cash"}, format="json"
        )
        assert res.status_code == 400

    def test_payment_on_draft_rejected(self, client_a, owner_a):
        inv = make_invoice(owner_a.business)
        res = client_a.post(f"/api/invoices/{inv.id}/payments/", {"amount": 100, "method": "cash"})
        assert res.status_code == 400

    def test_delete_payment_restores_balance(self, client_a, owner_a):
        inv = make_invoice(owner_a.business, send=True)
        pay = client_a.post(
            f"/api/invoices/{inv.id}/payments/", {"amount": 100, "method": "cash"}
        ).json()
        assert client_a.delete(f"/api/payments/{pay['id']}/").status_code == 204
        assert client_a.get(f"/api/invoices/{inv.id}/").json()["balance"] == 50000

    def test_overdue_boundary_uses_lusaka_date(self, owner_a, time_machine):
        inv = make_invoice(owner_a.business, send=True, due_date=dt.date(2026, 11, 15))
        # 21:59 UTC on the 15th is 23:59 in Lusaka (UTC+2): due today, not overdue yet.
        time_machine.move_to("2026-11-15T21:59:00Z")
        assert not Invoice.objects.with_balance().get(pk=inv.pk).is_overdue()
        # 22:00 UTC on the 15th is already the 16th in Lusaka.
        time_machine.move_to("2026-11-15T22:00:00Z")
        inv = Invoice.objects.with_balance().get(pk=inv.pk)
        assert inv.is_overdue()
        assert inv.display_status == "overdue"
        assert list(Invoice.objects.overdue()) == [inv]

    def test_status_filters(self, client_a, owner_a, time_machine):
        time_machine.move_to("2026-11-20T10:00:00Z")
        b = owner_a.business
        draft = make_invoice(b)
        overdue = make_invoice(b, send=True)
        paid = make_invoice(b, send=True, due_date=dt.date(2026, 12, 1))
        client_a.post(f"/api/invoices/{paid.id}/payments/", {"amount": 50000, "method": "cash"})

        def ids(status):
            return {
                i["id"] for i in client_a.get(f"/api/invoices/?status={status}").json()["results"]
            }

        assert ids("draft") == {draft.id}
        assert ids("overdue") == {overdue.id}
        assert ids("paid") == {paid.id}
        assert ids("unpaid") == {overdue.id}
        assert client_a.get("/api/invoices/?status=bogus").status_code == 400


@pytest.mark.django_db
class TestSending:
    def test_whatsapp_click_to_chat(self, client_a, owner_a):
        customer = CustomerFactory(
            business=owner_a.business, name="Mutale Phiri", phone="+260971234567"
        )
        inv = make_invoice(owner_a.business, customer=customer)
        res = client_a.post(f"/api/invoices/{inv.id}/whatsapp/")
        assert res.status_code == 200
        body = res.json()
        assert body["url"].startswith("https://wa.me/260971234567?text=Hello%20Mutale")
        assert str(inv.public_token) in body["message"]
        assert "K500.00" in body["message"]
        inv.refresh_from_db()
        assert inv.status == "sent"
        assert Delivery.objects.get(invoice=inv).status == "shared"

    def test_email_is_sent_with_pdf(self, client_a, owner_a, django_capture_on_commit_callbacks):
        inv = make_invoice(owner_a.business)
        with django_capture_on_commit_callbacks(execute=True):
            res = client_a.post(f"/api/invoices/{inv.id}/email/", {}, format="json")
        assert res.status_code == 202, res.content
        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert msg.to == [inv.customer.email]
        assert msg.subject == f"Invoice {inv.number} from {owner_a.business.name}"
        assert "Tax Invoice" not in msg.body
        name, content, mimetype = msg.attachments[0]
        assert (name, mimetype) == (f"{inv.number}.pdf", "application/pdf")
        assert content[:4] == b"%PDF"
        assert Delivery.objects.get(invoice=inv).status == "sent"
        assert ActivityLog.objects.filter(invoice=inv, verb="emailed").exists()

    def test_email_failure_is_recorded(
        self, client_a, owner_a, monkeypatch, django_capture_on_commit_callbacks
    ):
        from apps.messaging import tasks

        monkeypatch.setattr(tasks, "MAX_ATTEMPTS", 1)

        def boom(*a, **k):
            raise ConnectionError("SMTP down")

        monkeypatch.setattr("django.core.mail.EmailMultiAlternatives.send", boom)
        inv = make_invoice(owner_a.business)
        with django_capture_on_commit_callbacks(execute=True):
            client_a.post(f"/api/invoices/{inv.id}/email/", {}, format="json")
        delivery = Delivery.objects.get(invoice=inv)
        assert (delivery.status, delivery.error) == ("failed", "SMTP down")

    def test_email_needs_an_address(self, client_a, owner_a):
        customer = CustomerFactory(business=owner_a.business, email="")
        inv = make_invoice(owner_a.business, customer=customer)
        assert client_a.post(f"/api/invoices/{inv.id}/email/", {}, format="json").status_code == 400


@pytest.mark.django_db
class TestPublicPage:
    def test_customer_view_logs_viewed_once(self, api_client, owner_a):
        inv = make_invoice(owner_a.business, send=True)
        res = api_client.get(f"/i/{inv.public_token}/")
        assert res.status_code == 200
        html = res.content.decode()
        assert "<h1>Invoice</h1>" in html
        assert "Tax Invoice" not in html
        assert "K500.00" in html
        api_client.get(f"/i/{inv.public_token}/")
        assert ActivityLog.objects.filter(invoice=inv, verb="viewed").count() == 1
        inv.refresh_from_db()
        assert inv.viewed_at is not None

    def test_owner_preview_does_not_count_as_viewed(self, client_a, owner_a):
        inv = make_invoice(owner_a.business, send=True)
        assert client_a.get(f"/i/{inv.public_token}/").status_code == 200
        inv.refresh_from_db()
        assert inv.viewed_at is None

    def test_drafts_are_not_public(self, api_client, client_a, owner_a):
        inv = make_invoice(owner_a.business)
        assert api_client.get(f"/i/{inv.public_token}/").status_code == 404
        assert client_a.get(f"/i/{inv.public_token}/").status_code == 200  # owner preview

    def test_unknown_token_404(self, api_client):
        assert api_client.get("/i/00000000-0000-4000-8000-000000000000/").status_code == 404

    def test_pdf_download_is_cached(self, api_client, owner_a, settings):
        inv = make_invoice(owner_a.business, send=True)
        res = api_client.get(f"/i/{inv.public_token}/pdf/")
        assert res.status_code == 200
        assert res["Content-Type"] == "application/pdf"
        assert res.content[:4] == b"%PDF"
        files = list((settings.MEDIA_ROOT / "invoices").rglob("*.pdf"))
        assert len(files) == 1


@pytest.mark.django_db
def test_dashboard(client_a, owner_a, time_machine):
    time_machine.move_to("2026-11-20T10:00:00Z")
    b = owner_a.business
    debtor = CustomerFactory(business=b, name="Big Debtor")
    make_invoice(b, send=True, customer=debtor)  # overdue K500
    part = make_invoice(b, send=True, due_date=dt.date(2026, 12, 1))
    client_a.post(f"/api/invoices/{part.id}/payments/", {"amount": 10000, "method": "cash"})
    make_invoice(b)  # draft
    make_invoice(b, send=True, currency="USD", due_date=dt.date(2026, 12, 1))

    data = client_a.get("/api/dashboard/").json()
    owed = {r["currency"]: r["amount"] for r in data["owed"]}
    assert owed == {"ZMW": 90000, "USD": 50000}
    assert data["overdue"] == [{"currency": "ZMW", "amount": 50000, "count": 1}]
    assert data["paid_this_month"] == [{"currency": "ZMW", "amount": 10000, "count": 1}]
    assert data["drafts"] == 1
    assert data["top_debtors"][0]["name"] == "Big Debtor"


def test_invoice_quantity_decimal_roundtrip():
    from apps.invoices.models import InvoiceLine

    assert InvoiceLine(quantity=Decimal("0.333"), unit_price=5, discount=0).amount == 2


@pytest.mark.django_db
def test_send_survives_broker_outage(
    client_a, owner_a, settings, monkeypatch, django_capture_on_commit_callbacks
):
    from apps.messaging.tasks import send_invoice_email

    settings.CELERY_TASK_ALWAYS_EAGER = False

    def broker_down(*args, **kwargs):
        raise ConnectionRefusedError("redis down")

    monkeypatch.setattr(send_invoice_email, "delay", broker_down)
    inv = make_invoice(owner_a.business)
    with django_capture_on_commit_callbacks(execute=True):
        res = client_a.post(f"/api/invoices/{inv.id}/email/", {}, format="json")
    assert res.status_code == 202
    assert Delivery.objects.get(invoice=inv).status == "sent"  # ran inline
