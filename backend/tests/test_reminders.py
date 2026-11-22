import datetime as dt
from urllib.parse import unquote

import pytest
from django.core import mail

from apps.messaging.models import Delivery
from apps.messaging.reminders import send_due_reminders

from .factories import CustomerFactory, make_invoice

DUE = dt.date(2026, 11, 15)


@pytest.fixture
def reminding_business(owner_a):
    b = owner_a.business
    b.auto_reminders = True
    b.reminder_interval_days = 7
    b.max_reminders = 2
    b.save()
    return b


def run(day, capture):
    with capture(execute=True):
        return send_due_reminders(day)


@pytest.mark.django_db
class TestAutomaticReminders:
    def test_off_by_default(self, owner_a, django_capture_on_commit_callbacks):
        make_invoice(owner_a.business, send=True, due_date=DUE)
        assert run(dt.date(2026, 11, 20), django_capture_on_commit_callbacks) == 0

    def test_emails_overdue_invoice(self, reminding_business, django_capture_on_commit_callbacks):
        inv = make_invoice(reminding_business, send=True, due_date=DUE)
        assert run(DUE, django_capture_on_commit_callbacks) == 0  # due today: not overdue yet
        assert run(DUE + dt.timedelta(days=1), django_capture_on_commit_callbacks) == 1
        (msg,) = mail.outbox
        assert msg.subject.startswith(f"Reminder: invoice {inv.number}")
        assert "K500.00" in msg.body and "outstanding" in msg.body
        d = Delivery.objects.get(invoice=inv)
        assert (d.kind, d.automatic, d.status) == ("reminder", True, "sent")

    def test_interval_and_maximum(
        self, reminding_business, django_capture_on_commit_callbacks, time_machine
    ):
        make_invoice(reminding_business, send=True, due_date=DUE)
        counts = []
        for offset in [1, 3, 8, 9, 15, 30]:
            day = DUE + dt.timedelta(days=offset)
            time_machine.move_to(f"{day}T07:00:00Z")  # 09:00 in Lusaka, like the beat job
            counts.append(run(day, django_capture_on_commit_callbacks))
        # day 1: first; day 3: too soon; day 8: second (7 days later); day 9+: cap of 2 reached
        assert counts == [1, 0, 1, 0, 0, 0]

    def test_skips_paid_paused_draft_and_contactless(
        self, client_a, reminding_business, django_capture_on_commit_callbacks
    ):
        b = reminding_business
        paid = make_invoice(b, send=True, due_date=DUE)
        client_a.post(f"/api/invoices/{paid.id}/payments/", {"amount": 50000, "method": "cash"})
        paused = make_invoice(b, send=True, due_date=DUE)
        client_a.post(f"/api/invoices/{paused.id}/reminders/", {"paused": True}, format="json")
        make_invoice(b, due_date=DUE)  # draft
        nobody = CustomerFactory(business=b, phone="", email="")
        make_invoice(b, send=True, due_date=DUE, customer=nobody)
        assert run(DUE + dt.timedelta(days=2), django_capture_on_commit_callbacks) == 0

    def test_prefers_whatsapp_api_when_available(
        self, reminding_business, whatsapp_api, django_capture_on_commit_callbacks
    ):
        inv = make_invoice(reminding_business, send=True, due_date=DUE)
        run(DUE + dt.timedelta(days=1), django_capture_on_commit_callbacks)
        (payload,) = whatsapp_api.sent_payloads()
        assert payload["template"]["name"] == "invoice_reminder"
        assert Delivery.objects.get(invoice=inv, kind="reminder").channel == "whatsapp"

    def test_failed_reminders_dont_count_towards_cap(
        self, reminding_business, whatsapp_api, django_capture_on_commit_callbacks
    ):
        whatsapp_api.fail_with = (400, 131026)
        inv = make_invoice(reminding_business, send=True, due_date=DUE)
        run(DUE + dt.timedelta(days=1), django_capture_on_commit_callbacks)
        assert Delivery.objects.get(invoice=inv).status == "failed"
        whatsapp_api.fail_with = None
        assert run(DUE + dt.timedelta(days=2), django_capture_on_commit_callbacks) == 1


@pytest.mark.django_db
class TestManualReminder:
    def test_one_tap_whatsapp_link(self, client_a, owner_a):
        inv = make_invoice(owner_a.business, send=True, due_date=DUE)
        res = client_a.post(
            f"/api/invoices/{inv.id}/remind/", {"channel": "whatsapp_link"}, format="json"
        )
        assert res.status_code == 200
        text = unquote(res.json()["url"])
        assert "friendly reminder" in text and inv.number in text
        body = client_a.get(f"/api/invoices/{inv.id}/").json()
        assert body["reminder_count"] == 1
        assert any(a["verb"] == "reminded" for a in body["activity"])

    def test_cannot_remind_draft_or_paid(self, client_a, owner_a):
        draft = make_invoice(owner_a.business)
        res = client_a.post(f"/api/invoices/{draft.id}/remind/", {"channel": "whatsapp_link"})
        assert res.status_code == 400
        paid = make_invoice(owner_a.business, send=True)
        client_a.post(f"/api/invoices/{paid.id}/payments/", {"amount": 50000, "method": "cash"})
        res = client_a.post(f"/api/invoices/{paid.id}/remind/", {"channel": "whatsapp_link"})
        assert res.status_code == 400

    def test_pausing_works_on_sent_invoices(self, client_a, owner_a):
        inv = make_invoice(owner_a.business, send=True)
        res = client_a.post(f"/api/invoices/{inv.id}/reminders/", {"paused": True}, format="json")
        assert res.status_code == 200
        assert res.json()["reminders_paused"] is True


def test_beat_schedule_is_configured(settings):
    tasks = {v["task"] for v in settings.CELERY_BEAT_SCHEDULE.values()}
    assert tasks == {
        "apps.recurring.tasks.generate_recurring_invoices",
        "apps.messaging.tasks.send_overdue_reminders",
    }
