import hashlib
import hmac
import json

import pytest

from apps.audit.models import ActivityLog
from apps.messaging.models import Delivery, WebhookEvent

from .factories import CustomerFactory, make_invoice


def deliver(client, inv, **data):
    return client.post(f"/api/invoices/{inv.id}/deliver/", data, format="json")


@pytest.mark.django_db
class TestCloudApiSending:
    def test_config_reports_whatsapp_off_by_default(self, client_a):
        assert client_a.get("/api/config/").json() == {"whatsapp_api": False}

    def test_refuses_when_not_configured(self, client_a, owner_a):
        inv = make_invoice(owner_a.business)
        res = deliver(client_a, inv, channel="whatsapp")
        assert res.status_code == 400
        inv.refresh_from_db()
        assert inv.status == "draft"  # nothing half-done

    def test_sends_template_with_pdf(
        self, client_a, owner_a, whatsapp_api, django_capture_on_commit_callbacks
    ):
        assert client_a.get("/api/config/").json() == {"whatsapp_api": True}
        customer = CustomerFactory(business=owner_a.business, name="Mutale Phiri")
        inv = make_invoice(owner_a.business, customer=customer)
        with django_capture_on_commit_callbacks(execute=True):
            res = deliver(client_a, inv, channel="whatsapp")
        assert res.status_code == 202, res.content
        delivery = Delivery.objects.get(invoice=inv)
        assert (delivery.status, delivery.provider_message_id) == ("sent", "wamid.1")
        (payload,) = whatsapp_api.sent_payloads()
        assert payload["to"] == "260971234567"
        assert payload["template"]["name"] == "invoice_new"
        header, body = payload["template"]["components"]
        assert header["parameters"][0]["document"] == {
            "id": "media-1",
            "filename": f"{inv.number}.pdf",
        }
        texts = [p["text"] for p in body["parameters"]]
        assert texts[:4] == ["Mutale", owner_a.business.name, inv.number, "K500.00"]
        assert texts[5].endswith(f"/i/{inv.public_token}/")
        assert whatsapp_api.requests[0].headers["Authorization"] == "Bearer test-token"
        inv.refresh_from_db()
        assert inv.status == "sent"

    def test_permanent_error_fails_without_retry(
        self, client_a, owner_a, whatsapp_api, django_capture_on_commit_callbacks
    ):
        whatsapp_api.fail_with = (400, 131026)  # recipient can't receive
        inv = make_invoice(owner_a.business)
        with django_capture_on_commit_callbacks(execute=True):
            deliver(client_a, inv, channel="whatsapp")
        delivery = Delivery.objects.get(invoice=inv)
        assert (delivery.status, delivery.attempts) == ("failed", 1)
        assert ActivityLog.objects.filter(invoice=inv, verb="delivery_failed").exists()

    def test_transient_error_retries(
        self, client_a, owner_a, whatsapp_api, monkeypatch, django_capture_on_commit_callbacks
    ):
        from apps.messaging import tasks

        whatsapp_api.fail_with = (503, 2)
        retries = []

        def fake_retry(self, exc=None, **kw):
            retries.append(exc)
            return RuntimeError("retry scheduled")

        monkeypatch.setattr(tasks.send_delivery, "retry", fake_retry.__get__(tasks.send_delivery))
        inv = make_invoice(owner_a.business)
        with (
            pytest.raises(RuntimeError, match="retry scheduled"),
            django_capture_on_commit_callbacks(execute=True),
        ):
            deliver(client_a, inv, channel="whatsapp")
        assert len(retries) == 1
        delivery = Delivery.objects.get(invoice=inv)
        assert (delivery.status, delivery.attempts) == ("queued", 1)

    def test_customer_without_phone(self, client_a, owner_a, whatsapp_api):
        customer = CustomerFactory(business=owner_a.business, phone="")
        inv = make_invoice(owner_a.business, customer=customer)
        assert deliver(client_a, inv, channel="whatsapp").status_code == 400


def sign(body: bytes, secret="app-secret") -> str:  # noqa: S107
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def status_event(message_id, status, **extra):
    st = {"id": message_id, "status": status, "timestamp": "1764000000", **extra}
    return {"entry": [{"changes": [{"value": {"statuses": [st]}}]}]}


def post_webhook(client, payload, signature=None):
    body = json.dumps(payload).encode()
    return client.post(
        "/api/webhooks/whatsapp/",
        body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature if signature is not None else sign(body),
    )


@pytest.fixture
def sent_delivery(owner_a, whatsapp_api):
    inv = make_invoice(owner_a.business, send=True)
    return Delivery.objects.create(
        business=owner_a.business,
        invoice=inv,
        channel="whatsapp",
        recipient="+260971234567",
        status="sent",
        provider_message_id="wamid.ABC",
    )


@pytest.mark.django_db
class TestWhatsAppWebhook:
    def test_verification_handshake(self, api_client, whatsapp_api):
        ok = api_client.get(
            "/api/webhooks/whatsapp/",
            {"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "42"},
        )
        assert (ok.status_code, ok.content) == (200, b"42")
        bad = api_client.get(
            "/api/webhooks/whatsapp/",
            {"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "42"},
        )
        assert bad.status_code == 403

    @pytest.mark.parametrize("signature", ["", "sha256=deadbeef", sign(b"other body")])
    def test_invalid_signature_rejected(self, api_client, sent_delivery, signature):
        res = post_webhook(api_client, status_event("wamid.ABC", "delivered"), signature)
        assert res.status_code == 403
        sent_delivery.refresh_from_db()
        assert sent_delivery.status == "sent"

    def test_rejected_when_no_secret_configured(self, api_client, sent_delivery, settings):
        settings.WHATSAPP_APP_SECRET = ""
        res = post_webhook(api_client, status_event("wamid.ABC", "delivered"))
        assert res.status_code == 403

    def test_valid_events_update_delivery_and_timeline(self, api_client, sent_delivery):
        assert post_webhook(api_client, status_event("wamid.ABC", "delivered")).status_code == 200
        assert post_webhook(api_client, status_event("wamid.ABC", "read")).status_code == 200
        sent_delivery.refresh_from_db()
        assert sent_delivery.status == "read"
        verbs = list(
            ActivityLog.objects.filter(invoice=sent_delivery.invoice).values_list("verb", flat=True)
        )
        assert "delivered" in verbs and "read" in verbs

    def test_duplicate_event_is_ignored(self, api_client, sent_delivery):
        for _ in range(3):
            assert (
                post_webhook(api_client, status_event("wamid.ABC", "delivered")).status_code == 200
            )
        assert (
            ActivityLog.objects.filter(invoice=sent_delivery.invoice, verb="delivered").count() == 1
        )
        assert WebhookEvent.objects.count() == 1

    def test_status_never_moves_backwards(self, api_client, sent_delivery):
        post_webhook(api_client, status_event("wamid.ABC", "read"))
        post_webhook(api_client, status_event("wamid.ABC", "delivered"))  # arrives late
        sent_delivery.refresh_from_db()
        assert sent_delivery.status == "read"

    def test_failed_records_error(self, api_client, sent_delivery):
        payload = status_event(
            "wamid.ABC", "failed", errors=[{"code": 131026, "title": "Message undeliverable"}]
        )
        post_webhook(api_client, payload)
        sent_delivery.refresh_from_db()
        assert (sent_delivery.status, sent_delivery.error) == ("failed", "Message undeliverable")

    def test_unknown_message_is_acknowledged(self, api_client, whatsapp_api):
        assert post_webhook(api_client, status_event("wamid.UNKNOWN", "read")).status_code == 200


@pytest.mark.django_db
def test_email_tracking_events(owner_a):
    from anymail.signals import AnymailTrackingEvent, tracking

    inv = make_invoice(owner_a.business, send=True)
    delivery = Delivery.objects.create(
        business=owner_a.business,
        invoice=inv,
        channel="email",
        recipient="a@example.com",
        status="sent",
        provider_message_id="msg-1",
    )
    event = AnymailTrackingEvent(
        event_type="bounced", message_id="msg-1", event_id="ev-1", description="Mailbox full"
    )
    for _ in range(2):
        tracking.send(sender=object, event=event, esp_name="Resend")
    delivery.refresh_from_db()
    assert (delivery.status, delivery.error) == ("failed", "Mailbox full")
    assert ActivityLog.objects.filter(invoice=inv, verb="delivery_failed").count() == 1
