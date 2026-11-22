import hashlib
import hmac
import json

import pytest
from django.core import mail

from apps.audit.models import ActivityLog
from apps.payments import online
from apps.payments.models import LencoAccount, Payment, PaymentAttempt

from .factories import CustomerFactory, MembershipFactory, make_invoice


def signed(account, payload):
    body = json.dumps(payload).encode()
    key = hashlib.sha256(account.secret_key.encode()).hexdigest().encode()
    return body, hmac.new(key, body, hashlib.sha512).hexdigest()


def post_webhook(client, account, payload, signature=None):
    body, sig = signed(account, payload)
    return client.post(
        f"/api/webhooks/lenco/{account.webhook_id}/",
        body,
        content_type="application/json",
        HTTP_X_LENCO_SIGNATURE=signature if signature is not None else sig,
    )


def sent_invoice(business, **kw):
    customer = CustomerFactory(business=business, phone="+260961111111")
    return make_invoice(business, send=True, customer=customer, **kw)


@pytest.mark.django_db
class TestSettingsApi:
    def test_keys_are_write_only_and_encrypted(self, client_a, owner_a):
        res = client_a.get("/api/online-payments/")
        assert res.status_code == 200
        assert res.json()["enabled"] is False
        res = client_a.put(
            "/api/online-payments/",
            {"enabled": True, "public_key": "pub-123", "secret_key": "sk-live-abcdef1234"},
            format="json",
        )
        assert res.status_code == 200, res.content
        body = res.json()
        assert "secret_key" not in body
        assert body["has_secret_key"] is True and body["secret_key_hint"] == "…1234"
        assert body["webhook_url"].startswith("https://app.example.com/api/webhooks/lenco/")
        account = LencoAccount.objects.get(business=owner_a.business)
        assert "sk-live" not in account.secret_key_encrypted
        assert account.secret_key == "sk-live-abcdef1234"
        # Saving again without the secret keeps it
        client_a.put("/api/online-payments/", {"public_key": "pub-456"}, format="json")
        account.refresh_from_db()
        assert (account.public_key, account.secret_key) == ("pub-456", "sk-live-abcdef1234")

    def test_enabling_needs_keys(self, client_a):
        res = client_a.put("/api/online-payments/", {"enabled": True}, format="json")
        assert res.status_code == 400
        assert "public_key" in res.json()

    def test_only_owners_and_admins_can_change(self, owner_a):
        from rest_framework.test import APIClient

        member = MembershipFactory(business=owner_a.business, role="staff")
        client = APIClient()
        client.force_login(member.user)
        assert client.get("/api/online-payments/").status_code == 200
        res = client.put("/api/online-payments/", {"public_key": "x"}, format="json")
        assert res.status_code == 403

    def test_each_business_has_its_own_account(self, client_a, owner_b, lenco_account):
        from rest_framework.test import APIClient

        other = APIClient()
        other.force_login(owner_b.user)
        body = other.get("/api/online-payments/").json()
        assert body["enabled"] is False and body["has_secret_key"] is False
        assert str(lenco_account.webhook_id) not in body["webhook_url"]

    def test_connection_test(self, client_a, lenco_account, lenco_api):
        assert client_a.post("/api/online-payments/test/").json()["ok"] is True  # 404 = authed
        lenco_api.error = (401, "Invalid token")
        res = client_a.post("/api/online-payments/test/").json()
        assert res["ok"] is False and "secret key" in res["message"]

    def test_config_reports_online_payments(self, client_a, lenco_account):
        assert client_a.get("/api/config/").json()["online_payments"] is True


@pytest.mark.django_db
class TestPayNowPage:
    def test_shown_only_when_payable(self, client, owner_a, lenco_account):
        inv = sent_invoice(owner_a.business)
        html = client.get(inv.public_path).content.decode()
        assert "Pay K500.00 now" in html and 'value="0961111111"' in html
        assert 'value="mtn" checked' in html  # 096 → MTN

        usd = sent_invoice(owner_a.business, currency="USD")
        assert "Pay with mobile money" not in client.get(usd.public_path).content.decode()

        lenco_account.enabled = False
        lenco_account.save()
        assert "Pay with mobile money" not in client.get(inv.public_path).content.decode()

    def test_hidden_without_account(self, client, owner_a):
        inv = sent_invoice(owner_a.business)
        assert "Pay with mobile money" not in client.get(inv.public_path).content.decode()

    def test_csrf_and_referrer_policy(self, owner_a, lenco_account, lenco_api):
        from django.test import Client

        inv = sent_invoice(owner_a.business)
        browser = Client(enforce_csrf_checks=True)
        page = browser.get(inv.public_path)
        assert page["Referrer-Policy"] == "same-origin"
        res = browser.post(inv.public_path + "pay/", {"operator": "mtn", "phone": "0961111111"})
        assert res.status_code == 403  # no token
        token = browser.cookies["csrftoken"].value
        res = browser.post(
            inv.public_path + "pay/",
            {"operator": "mtn", "phone": "0961111111", "csrfmiddlewaretoken": token},
        )
        assert res.status_code == 302


@pytest.mark.django_db
class TestMobileMoney:
    def test_happy_path(
        self, client, owner_a, lenco_account, lenco_api, django_capture_on_commit_callbacks
    ):
        inv = sent_invoice(owner_a.business)
        res = client.post(inv.public_path + "pay/", {"operator": "mtn", "phone": "096 111 1111"})
        assert res.status_code == 302
        attempt = PaymentAttempt.objects.get()
        assert res["Location"] == f"{inv.public_path}pay/{attempt.reference}/"
        assert attempt.reference.startswith(inv.number + "-")
        body = lenco_api.bodies()[0]
        assert body == {
            "reference": attempt.reference,
            "amount": 500.0,  # major units
            "phone": "0961111111",
            "operator": "mtn",
            "country": "zm",
            "bearer": "merchant",
        }
        assert lenco_api.requests[0].headers["Authorization"] == "Bearer sk-test-secret-0000"
        assert attempt.status == "pay_offline"

        page = client.get(res["Location"]).content.decode()
        assert "Check your phone" in page and 'http-equiv="refresh"' in page

        lenco_api.statuses[attempt.reference] = lenco_api.data(attempt.reference, "successful")
        attempt.last_checked_at = None
        attempt.save()
        with django_capture_on_commit_callbacks(execute=True):
            page = client.get(res["Location"]).content.decode()
        assert "Payment received" in page and "View your receipt" in page

        payment = Payment.objects.get()
        assert (payment.amount, payment.method, payment.source) == (50000, "mtn_momo", "online")
        assert payment.receipt_number == f"RCT-{payment.paid_on.year}-0001"
        inv.refresh_from_db()
        assert inv.balance == 0 and inv.display_status == "paid"
        assert ActivityLog.objects.filter(invoice=inv, verb="paid_online").count() == 1
        subjects = sorted(m.subject for m in mail.outbox)
        assert subjects[0].startswith("Paid: " + inv.number)
        assert subjects[1].startswith("Receipt RCT-")
        owner_mail = next(m for m in mail.outbox if m.subject.startswith("Paid"))
        assert owner_mail.to == [owner_a.business.email]

    def test_failed_collection(self, client, owner_a, lenco_account, lenco_api):
        inv = sent_invoice(owner_a.business)
        lenco_api.collect = {"status": "failed", "reasonForFailure": "Not enough funds"}
        res = client.post(inv.public_path + "pay/", {"operator": "mtn", "phone": "0962222222"})
        page = client.get(res["Location"]).content.decode()
        assert "Not enough funds" in page and "Try again" in page
        assert not Payment.objects.exists()
        assert ActivityLog.objects.filter(invoice=inv, verb="online_payment_failed").exists()

    def test_lenco_unreachable(self, client, owner_a, lenco_account, lenco_api):
        inv = sent_invoice(owner_a.business)
        lenco_api.error = (500, "Server error")
        res = client.post(inv.public_path + "pay/", {"operator": "airtel", "phone": "0971111111"})
        attempt = PaymentAttempt.objects.get()
        assert attempt.status == "failed" and "Server error" in attempt.failure_reason
        assert "didn't go through" in client.get(res["Location"]).content.decode()

    def test_bad_phone_shows_form_again(self, client, owner_a, lenco_account, lenco_api):
        inv = sent_invoice(owner_a.business)
        res = client.post(inv.public_path + "pay/", {"operator": "mtn", "phone": "12"})
        assert res.status_code == 400
        assert "valid Zambian mobile money number" in res.content.decode()
        assert not lenco_api.requests

    def test_refresh_is_throttled(self, client, owner_a, lenco_account, lenco_api):
        inv = sent_invoice(owner_a.business)
        res = client.post(inv.public_path + "pay/", {"operator": "mtn", "phone": "0961111111"})
        for _ in range(3):
            client.get(res["Location"])
        assert len(lenco_api.requests) == 1  # just checked when it was started


@pytest.mark.django_db
class TestWebhook:
    def start(self, client, inv):
        client.post(inv.public_path + "pay/", {"operator": "mtn", "phone": "0961111111"})
        return PaymentAttempt.objects.get(invoice=inv)

    def test_success_is_applied_once(self, client, owner_a, lenco_account, lenco_api):
        inv = sent_invoice(owner_a.business)
        attempt = self.start(client, inv)
        payload = {
            "event": "collection.successful",
            "data": lenco_api.data(attempt.reference, "successful"),
        }
        assert post_webhook(client, lenco_account, payload).status_code == 200
        assert post_webhook(client, lenco_account, payload).status_code == 200  # replay
        # and the customer's page polling afterwards doesn't double count either
        lenco_api.statuses[attempt.reference] = payload["data"]
        online.refresh(PaymentAttempt.objects.get(pk=attempt.pk), force=True)
        assert Payment.objects.count() == 1
        attempt.refresh_from_db()
        assert attempt.status == "successful" and attempt.payment is not None

    def test_bad_signature_rejected(self, client, owner_a, lenco_account, lenco_api):
        inv = sent_invoice(owner_a.business)
        attempt = self.start(client, inv)
        payload = {
            "event": "collection.successful",
            "data": lenco_api.data(attempt.reference, "successful"),
        }
        assert post_webhook(client, lenco_account, payload, signature="0" * 128).status_code == 401
        assert post_webhook(client, lenco_account, payload, signature="").status_code == 401
        assert not Payment.objects.exists()

    def test_other_business_key_cannot_sign(self, client, owner_a, owner_b, lenco_account):
        other = LencoAccount(business=owner_b.business, enabled=True, public_key="p")
        other.secret_key = "someone-elses-key"
        other.save()
        inv = sent_invoice(owner_a.business)
        attempt = PaymentAttempt.objects.create(
            business=owner_a.business,
            invoice=inv,
            reference="X-1",
            channel="mobile_money",
            amount=50000,
        )
        body, sig = signed(
            other, {"event": "collection.successful", "data": {"reference": attempt.reference}}
        )
        res = client.post(
            f"/api/webhooks/lenco/{lenco_account.webhook_id}/",
            body,
            content_type="application/json",
            HTTP_X_LENCO_SIGNATURE=sig,
        )
        assert res.status_code == 401
        # And a valid event on B's URL can't touch A's attempt (looked up within B only)
        res = client.post(
            f"/api/webhooks/lenco/{other.webhook_id}/",
            body,
            content_type="application/json",
            HTTP_X_LENCO_SIGNATURE=sig,
        )
        assert res.status_code == 200
        assert not Payment.objects.exists()

    def test_unknown_reference_and_other_events_acknowledged(self, client, lenco_account):
        for payload in (
            {"event": "collection.successful", "data": {"reference": "made-in-dashboard"}},
            {"event": "transfer.successful", "data": {"reference": "x"}},
        ):
            assert post_webhook(client, lenco_account, payload).status_code == 200
        assert not Payment.objects.exists()

    def test_customer_paid_twice_records_overpayment(
        self, client, owner_a, lenco_account, lenco_api
    ):
        inv = sent_invoice(owner_a.business)
        first = self.start(client, inv)
        client.post(inv.public_path + "pay/", {"operator": "mtn", "phone": "0961111111"})
        second = PaymentAttempt.objects.exclude(pk=first.pk).get()
        for attempt in (first, second):
            payload = {
                "event": "collection.successful",
                "data": lenco_api.data(attempt.reference, "successful"),
            }
            post_webhook(client, lenco_account, payload)
        assert Payment.objects.count() == 2
        assert ActivityLog.objects.filter(invoice=inv, message__startswith="Overpaid by K500.00")


@pytest.mark.django_db
class TestCardAndReconcile:
    def test_card_attempt_checks_after_widget(self, client, owner_a, lenco_account, lenco_api):
        inv = sent_invoice(owner_a.business)
        res = client.post(inv.public_path + "pay/", {"method": "card", "email": "a@b.co"})
        attempt = PaymentAttempt.objects.get()
        assert attempt.channel == "card" and not lenco_api.requests
        page = client.get(res["Location"]).content.decode()
        assert "pay.sandbox.lenco.co/js/v1/inline.js" in page
        options = json.loads(
            page.split('id="lenco-options" type="application/json">')[1].split("</script>")[0]
        )
        assert options["key"] == "pub-test-key" and options["reference"] == attempt.reference
        assert (options["amount"], options["currency"], options["email"]) == (
            500.0,
            "ZMW",
            "a@b.co",
        )
        assert not lenco_api.requests  # untouched widget: no API calls
        # Widget closed before Lenco confirmed: status 404 keeps it open
        page = client.get(res["Location"] + "?check=1").content.decode()
        assert "Confirming your card payment" in page
        lenco_api.statuses[attempt.reference] = lenco_api.data(
            attempt.reference, "successful", type="card", mobileMoneyDetails=None
        )
        attempt.refresh_from_db()
        attempt.last_checked_at = None
        attempt.save()
        assert "Payment received" in client.get(res["Location"] + "?check=1").content.decode()
        assert Payment.objects.get().method == "card"

    def test_reconcile_settles_missed_webhooks(self, client, owner_a, lenco_account, lenco_api):
        import datetime as dt

        from django.utils import timezone

        inv = sent_invoice(owner_a.business)
        client.post(inv.public_path + "pay/", {"operator": "mtn", "phone": "0961111111"})
        attempt = PaymentAttempt.objects.get()
        lenco_api.statuses[attempt.reference] = lenco_api.data(attempt.reference, "successful")
        later = timezone.now() + dt.timedelta(minutes=5)
        assert online.reconcile_open_attempts(later) == 1
        assert Payment.objects.count() == 1
        # Abandoned card attempts are closed after a day
        old = PaymentAttempt.objects.create(
            business=owner_a.business, invoice=inv, reference="old", channel="card", amount=1
        )
        online.reconcile_open_attempts(timezone.now() + dt.timedelta(days=2))
        old.refresh_from_db()
        assert old.status == "failed"


@pytest.mark.django_db
class TestPaymentsAndReceipts:
    def test_online_payment_cannot_be_deleted(self, client_a, owner_a, lenco_account, lenco_api):
        from django.test import Client

        inv = sent_invoice(owner_a.business)
        Client().post(inv.public_path + "pay/", {"operator": "mtn", "phone": "0961111111"})
        attempt = PaymentAttempt.objects.get()
        online.apply_collection(attempt, lenco_api.data(attempt.reference, "successful"))
        payment = Payment.objects.get()
        res = client_a.delete(f"/api/payments/{payment.id}/")
        assert res.status_code == 400
        assert Payment.objects.exists()

    def test_manual_payments_get_receipts(self, client_a, client, owner_a, time_machine):
        time_machine.move_to("2026-11-20T10:00:00Z")
        inv = sent_invoice(owner_a.business)
        for amount in (20000, 30000):
            res = client_a.post(
                f"/api/invoices/{inv.id}/payments/",
                {"amount": amount, "method": "cash"},
                format="json",
            )
            assert res.status_code == 201
        detail = client_a.get(f"/api/invoices/{inv.id}/").json()
        numbers = sorted(p["receipt_number"] for p in detail["payments"])
        assert numbers == ["RCT-2026-0001", "RCT-2026-0002"]
        receipt_url = detail["payments"][0]["receipt_url"]
        assert receipt_url.startswith("https://app.example.com/r/")
        path = receipt_url.removeprefix("https://app.example.com")
        page = client.get(path)
        assert page.status_code == 200
        html = page.content.decode()
        assert "<h1>Receipt</h1>" in html and inv.number in html and "Tax Invoice" not in html
        pdf = client.get(path + "pdf/")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        # The invoice page lists the receipts
        assert "RCT-2026-0001" in client.get(inv.public_path).content.decode()

    def test_unknown_receipt_404(self, client):
        assert client.get("/r/00000000-0000-0000-0000-000000000000/").status_code == 404
