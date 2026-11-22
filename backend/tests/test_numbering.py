import threading

import pytest
from django.db import connection

from apps.invoices.models import Invoice

from .factories import CustomerFactory, MembershipFactory, make_invoice

N = 50


@pytest.mark.django_db(transaction=True)
def test_concurrent_creation_gets_unique_consecutive_numbers():
    business = MembershipFactory().business
    customer = CustomerFactory(business=business)
    barrier = threading.Barrier(N)
    errors: list[BaseException] = []

    def worker():
        try:
            barrier.wait()
            make_invoice(business, customer=customer)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    numbers = sorted(Invoice.objects.filter(business=business).values_list("number", flat=True))
    assert numbers == [f"INV-2026-{i:04d}" for i in range(1, N + 1)]


@pytest.mark.django_db
def test_numbering_is_per_business_and_per_year():
    import datetime as dt

    a = MembershipFactory().business
    b = MembershipFactory().business
    assert make_invoice(a).number == "INV-2026-0001"
    assert make_invoice(b).number == "INV-2026-0001"
    assert make_invoice(a).number == "INV-2026-0002"
    nxt = make_invoice(a, issue_date=dt.date(2027, 1, 2), due_date=dt.date(2027, 1, 30))
    assert nxt.number == "INV-2027-0001"
