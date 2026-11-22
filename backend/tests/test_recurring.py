import datetime as dt

import pytest
from django.core import mail

from apps.audit.models import ActivityLog
from apps.invoices.models import Invoice
from apps.recurring.models import RecurringInvoice, add_months
from apps.recurring.services import generate_for, generate_recurring

from .factories import CustomerFactory, MembershipFactory

LINES = [
    {"description": "Monthly cleaning", "quantity": "1", "unit_price": 120000},
    {"description": "Supplies", "quantity": "2.5", "unit_price": 1000, "discount": 500},
]


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (dt.date(2026, 1, 31), 1, dt.date(2026, 2, 28)),
        (dt.date(2026, 1, 31), 2, dt.date(2026, 3, 31)),  # anchored to the 31st, no drift
        (dt.date(2028, 1, 31), 1, dt.date(2028, 2, 29)),  # leap year
        (dt.date(2026, 11, 15), 3, dt.date(2027, 2, 15)),
    ],
)
def test_add_months(start, months, expected):
    assert add_months(start, months) == expected


def make_schedule(business, **kw):
    defaults = dict(
        customer=CustomerFactory(business=business),
        frequency="monthly",
        interval=1,
        start_date=dt.date(2026, 12, 1),
        next_run_date=kw.get("start_date", dt.date(2026, 12, 1)),
        days_until_due=10,
        lines=LINES,
    )
    defaults.update(kw)
    return RecurringInvoice.objects.create(business=business, **defaults)


@pytest.mark.django_db
class TestApi:
    def test_create_and_preview(self, client_a, owner_a, time_machine):
        time_machine.move_to("2026-11-22T10:00:00Z")
        customer = CustomerFactory(business=owner_a.business)
        res = client_a.post(
            "/api/recurring/",
            {
                "customer_id": customer.id,
                "frequency": "monthly",
                "start_date": "2026-12-01",
                "days_until_due": 10,
                "lines": LINES,
                "send_mode": "email",
            },
            format="json",
        )
        assert res.status_code == 201, res.content
        body = res.json()
        assert body["next_run_date"] == "2026-12-01"
        assert body["upcoming"] == ["2026-12-01", "2027-01-01", "2027-02-01"]
        assert body["total"] == 120000 + 2500 - 500
        assert body["lines"][1]["quantity"] == "2.500"

    def test_rejects_start_in_the_past_and_bad_lines(self, client_a, owner_a, time_machine):
        time_machine.move_to("2026-11-22T10:00:00Z")
        customer = CustomerFactory(business=owner_a.business)
        base = {"customer_id": customer.id, "frequency": "weekly", "lines": LINES}
        res = client_a.post("/api/recurring/", {**base, "start_date": "2026-11-01"}, format="json")
        assert res.status_code == 400
        bad = [{"description": "x", "quantity": "0", "unit_price": 100}]
        res = client_a.post(
            "/api/recurring/", {**base, "start_date": "2026-12-01", "lines": bad}, format="json"
        )
        assert res.status_code == 400

    def test_tenant_isolation(self, client_a, owner_b):
        other = make_schedule(owner_b.business)
        assert client_a.get(f"/api/recurring/{other.id}/").status_code == 404
        assert client_a.delete(f"/api/recurring/{other.id}/").status_code == 404
        res = client_a.post(
            "/api/recurring/",
            {
                "customer_id": other.customer_id,
                "frequency": "weekly",
                "start_date": "2030-01-01",
                "lines": LINES,
            },
            format="json",
        )
        assert res.status_code == 400

    def test_resume_skips_dates_missed_while_paused(self, client_a, owner_a, time_machine):
        s = make_schedule(owner_a.business, frequency="weekly", is_active=False)
        time_machine.move_to("2026-12-03T10:00:00Z")
        res = client_a.patch(f"/api/recurring/{s.id}/", {"is_active": True}, format="json")
        assert res.status_code == 200, res.content
        assert res.json()["next_run_date"] == "2026-12-08"  # not the missed Dec 1
        assert generate_recurring(dt.date(2026, 12, 3)) == 0


@pytest.mark.django_db
class TestGeneration:
    def test_generates_on_run_date_and_advances(self, owner_a):
        s = make_schedule(owner_a.business)
        assert generate_recurring(dt.date(2026, 11, 30)) == 0
        assert generate_recurring(dt.date(2026, 12, 1)) == 1
        inv = Invoice.objects.get(recurring=s)
        assert (inv.issue_date, inv.due_date, inv.status) == (
            dt.date(2026, 12, 1),
            dt.date(2026, 12, 11),
            "draft",
        )
        assert inv.total == 122000
        assert inv.lines.count() == 2
        assert ActivityLog.objects.filter(invoice=inv, verb="generated").exists()
        s.refresh_from_db()
        assert (s.runs, s.next_run_date) == (1, dt.date(2027, 1, 1))

    def test_running_twice_is_harmless(self, owner_a):
        s = make_schedule(owner_a.business)
        generate_recurring(dt.date(2026, 12, 1))
        generate_recurring(dt.date(2026, 12, 1))
        # Even if the schedule's counter were rolled back, the DB refuses a second invoice.
        RecurringInvoice.objects.filter(pk=s.pk).update(runs=0, next_run_date=dt.date(2026, 12, 1))
        generate_for(s.pk, dt.date(2026, 12, 1))
        assert Invoice.objects.filter(recurring=s).count() == 1

    def test_catches_up_after_downtime(self, owner_a):
        s = make_schedule(owner_a.business, frequency="weekly", start_date=dt.date(2026, 12, 1))
        assert generate_recurring(dt.date(2026, 12, 22)) == 4  # 1, 8, 15, 22
        dates = sorted(Invoice.objects.filter(recurring=s).values_list("issue_date", flat=True))
        assert dates[-1] == dt.date(2026, 12, 22)

    def test_end_date_stops_schedule(self, owner_a):
        s = make_schedule(owner_a.business, end_date=dt.date(2027, 1, 15))
        generate_recurring(dt.date(2027, 3, 1))
        s.refresh_from_db()
        assert Invoice.objects.filter(recurring=s).count() == 2  # Dec 1, Jan 1
        assert s.is_active is False

    def test_paused_schedule_does_nothing(self, owner_a):
        make_schedule(owner_a.business, is_active=False)
        assert generate_recurring(dt.date(2027, 1, 1)) == 0

    def test_auto_email_sends_latest_only(self, owner_a, django_capture_on_commit_callbacks):
        s = make_schedule(owner_a.business, send_mode="email", frequency="weekly")
        with django_capture_on_commit_callbacks(execute=True):
            generate_recurring(dt.date(2026, 12, 8))
        invoices = Invoice.objects.filter(recurring=s).order_by("issue_date")
        assert [i.status for i in invoices] == ["draft", "sent"]
        assert len(mail.outbox) == 1

    def test_auto_whatsapp_without_setup_leaves_draft(self, owner_a):
        s = make_schedule(owner_a.business, send_mode="whatsapp")
        generate_recurring(dt.date(2026, 12, 1))
        inv = Invoice.objects.get(recurring=s)
        assert inv.status == "draft"
        assert ActivityLog.objects.filter(invoice=inv, verb="delivery_failed").exists()

    def test_numbering_shared_with_manual_invoices(self):
        b = MembershipFactory().business
        make_schedule(b)
        generate_recurring(dt.date(2026, 12, 1))
        assert Invoice.objects.get(business=b).number == "INV-2026-0001"
