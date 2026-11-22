import datetime as dt

import pytest
from django.core import mail

from apps.audit.models import ActivityLog
from apps.quotes.models import Quote
from apps.quotes.services import create_quote, send_quote

from .factories import CustomerFactory, make_invoice


def make_quote(business, *, send=False, **fields):
    from decimal import Decimal

    fields.setdefault("customer", CustomerFactory(business=business))
    fields.setdefault("issue_date", dt.date(2026, 11, 1))
    fields.setdefault("valid_until", dt.date(2026, 12, 1))
    lines = [{"description": "Wedding hair", "quantity": Decimal("3"), "unit_price": 40000}]
    quote = create_quote(business, None, lines=lines, **fields)
    return send_quote(quote, None) if send else quote


@pytest.mark.django_db
class TestQuotes:
    def test_create_via_api_has_own_numbering(self, client_a, owner_a):
        make_invoice(owner_a.business)
        customer = CustomerFactory(business=owner_a.business)
        res = client_a.post(
            "/api/quotes/",
            {
                "customer_id": customer.id,
                "issue_date": "2026-11-01",
                "valid_until": "2026-11-30",
                "lines": [{"description": "x", "quantity": "2", "unit_price": 1500}],
            },
            format="json",
        )
        assert res.status_code == 201, res.content
        assert (res.json()["number"], res.json()["total"]) == ("QUO-2026-0001", 3000)
        assert make_invoice(owner_a.business).number == "INV-2026-0002"

    def test_customer_accepts_on_public_page(self, client, owner_a, time_machine):
        time_machine.move_to("2026-11-10T10:00:00Z")
        q = make_quote(owner_a.business, send=True)
        page = client.get(f"/q/{q.public_token}/")
        assert page.status_code == 200
        html = page.content.decode()
        assert "<h1>Quote</h1>" in html and "Accept quote" in html and "K1,200.00" in html
        # no-referrer would make browsers send Origin: null and fail CSRF on the form
        assert page["Referrer-Policy"] == "same-origin"
        res = client.post(f"/q/{q.public_token}/respond/", {"decision": "accept"})
        assert res.status_code == 302
        q.refresh_from_db()
        assert q.status == "accepted" and q.viewed_at is not None
        assert "Accepted." in client.get(f"/q/{q.public_token}/").content.decode()
        verbs = set(ActivityLog.objects.filter(quote=q).values_list("verb", flat=True))
        assert {"viewed", "accepted"} <= verbs

    def test_public_response_needs_csrf(self, owner_a):
        from django.test import Client

        q = make_quote(owner_a.business, send=True)
        res = Client(enforce_csrf_checks=True).post(
            f"/q/{q.public_token}/respond/", {"decision": "accept"}
        )
        assert res.status_code == 403

    def test_customer_declines(self, client, owner_a, time_machine):
        time_machine.move_to("2026-11-10T10:00:00Z")
        q = make_quote(owner_a.business, send=True)
        client.post(f"/q/{q.public_token}/respond/", {"decision": "decline"})
        q.refresh_from_db()
        assert q.status == "declined"

    def test_expired_quote_cannot_be_accepted(self, client, owner_a, time_machine):
        q = make_quote(owner_a.business, send=True)
        time_machine.move_to("2026-12-02T10:00:00Z")
        assert Quote.objects.get(pk=q.pk).display_status == "expired"
        res = client.post(f"/q/{q.public_token}/respond/", {"decision": "accept"})
        assert res["Location"].endswith("?error=closed")
        q.refresh_from_db()
        assert q.status == "sent"

    def test_drafts_are_not_public(self, client, owner_a):
        q = make_quote(owner_a.business)
        assert client.get(f"/q/{q.public_token}/").status_code == 404
        assert (
            client.post(f"/q/{q.public_token}/respond/", {"decision": "accept"}).status_code == 404
        )

    def test_convert_to_invoice(self, client_a, owner_a, time_machine):
        time_machine.move_to("2026-11-10T10:00:00Z")
        q = make_quote(owner_a.business, send=True)
        res = client_a.post(f"/api/quotes/{q.id}/convert/", {"days_until_due": 7}, format="json")
        assert res.status_code == 201, res.content
        inv = client_a.get(f"/api/invoices/{res.json()['id']}/").json()
        assert inv["status"] == "draft" and inv["total"] == 120000
        assert inv["due_date"] == "2026-11-17"
        assert inv["from_quote"]["number"] == q.number
        quote = client_a.get(f"/api/quotes/{q.id}/").json()
        assert quote["status"] == "converted"
        assert quote["converted_invoice"]["id"] == inv["id"]
        assert client_a.post(f"/api/quotes/{q.id}/convert/").status_code == 400

    def test_cannot_convert_declined(self, client_a, owner_a):
        q = make_quote(owner_a.business, send=True)
        client_a.post(f"/api/quotes/{q.id}/respond/", {"accepted": False}, format="json")
        assert client_a.post(f"/api/quotes/{q.id}/convert/").status_code == 400

    def test_answered_quote_is_locked(self, client_a, owner_a):
        q = make_quote(owner_a.business, send=True)
        client_a.post(f"/api/quotes/{q.id}/respond/", {"accepted": True}, format="json")
        res = client_a.patch(f"/api/quotes/{q.id}/", {"notes": "x"}, format="json")
        assert res.status_code == 400

    def test_send_by_whatsapp_link_and_email(
        self, client_a, owner_a, django_capture_on_commit_callbacks
    ):
        q = make_quote(owner_a.business)
        res = client_a.post(
            f"/api/quotes/{q.id}/deliver/", {"channel": "whatsapp_link"}, format="json"
        )
        assert res.status_code == 200
        assert "quote" in res.json()["message"] and str(q.public_token) in res.json()["url"]
        with django_capture_on_commit_callbacks(execute=True):
            res = client_a.post(f"/api/quotes/{q.id}/deliver/", {"channel": "email"}, format="json")
        assert res.status_code == 202
        (msg,) = mail.outbox
        assert msg.subject == f"Quote {q.number} from {owner_a.business.name}"
        assert msg.attachments[0][0] == f"{q.number}.pdf"

    def test_status_filters(self, client_a, owner_a, time_machine):
        time_machine.move_to("2026-11-10T10:00:00Z")
        draft = make_quote(owner_a.business)
        sent = make_quote(owner_a.business, send=True)
        expired = make_quote(owner_a.business, send=True, valid_until=dt.date(2026, 11, 5))

        def ids(s):
            return {q["id"] for q in client_a.get(f"/api/quotes/?status={s}").json()["results"]}

        assert ids("draft") == {draft.id}
        assert ids("sent") == {sent.id}
        assert ids("expired") == {expired.id}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("get", ""),
        ("patch", ""),
        ("post", "send/"),
        ("post", "convert/"),
        ("post", "deliver/"),
        ("post", "respond/"),
        ("get", "pdf/"),
    ],
)
def test_quote_tenant_isolation(client_a, owner_b, method, suffix):
    q = make_quote(owner_b.business, send=True)
    res = getattr(client_a, method)(
        f"/api/quotes/{q.id}/{suffix}",
        {"channel": "whatsapp_link", "accepted": True},
        format="json",
    )
    assert res.status_code == 404
