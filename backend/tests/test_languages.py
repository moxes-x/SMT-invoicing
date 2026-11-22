import pytest

from apps.core.i18n import STRINGS, Language, t
from apps.messaging.services import content_for

from .factories import CustomerFactory, make_invoice

pytestmark = pytest.mark.django_db


def test_every_string_has_all_three_languages_and_same_placeholders():
    import string

    for key, row in STRINGS.items():
        assert len(row) == 3 and all(row), key
        fields = [{f for _, f, _, _ in string.Formatter().parse(text) if f} for text in row]
        assert fields[0] == fields[1] == fields[2], key


def test_unknown_language_falls_back_to_english():
    assert t("xx", "total") == "Total"
    assert t(None, "hello_name", name="Mwila") == "Hello Mwila,"


@pytest.mark.parametrize(
    ("lang", "expected"),
    [("en", "Hello Bwalya, here is invoice"), ("bem", "Mwapoleni Bwalya,"), ("ny", "Muli bwanji")],
)
def test_whatsapp_message_in_customer_language(owner_a, lang, expected):
    customer = CustomerFactory(business=owner_a.business, name="Bwalya Tembo", language=lang)
    inv = make_invoice(owner_a.business, customer=customer, send=True)
    content = content_for(inv, "invoice")
    assert content.text.startswith(expected)
    assert inv.public_url in content.text
    # Cloud API templates are approved in English: their parameters don't change.
    assert content.params[0] == "Bwalya"


def test_reminder_and_quote_messages_translate(owner_a):
    from apps.quotes.services import create_quote

    customer = CustomerFactory(business=owner_a.business, language=Language.NYANJA)
    inv = make_invoice(owner_a.business, customer=customer, send=True)
    assert "chikumbutso" in content_for(inv, "reminder").text
    import datetime as dt
    from decimal import Decimal

    quote = create_quote(
        owner_a.business,
        owner_a.user,
        customer=customer,
        valid_until=dt.date(2030, 1, 1),
        lines=[{"description": "x", "quantity": Decimal("1"), "unit_price": 100}],
    )
    assert "mtengo (quote)" in content_for(quote, "quote").text


def test_public_invoice_page_in_bemba(client, owner_a):
    customer = CustomerFactory(business=owner_a.business, language=Language.BEMBA)
    inv = make_invoice(owner_a.business, customer=customer, send=True)
    html = client.get(f"/i/{inv.public_token}/").content.decode()
    assert '<html lang="bem">' in html
    assert "Ifyashala ukulipila" in html  # balance due
    assert "<h1>Invoice</h1>" in html  # the document name stays English
    assert ">Cacelwa<" in html  # "overdue" badge (the factory invoice is past due)


def test_public_quote_page_in_nyanja(client, owner_a):
    import datetime as dt
    from decimal import Decimal

    from apps.quotes.services import create_quote, send_quote

    customer = CustomerFactory(business=owner_a.business, language=Language.NYANJA)
    quote = create_quote(
        owner_a.business,
        owner_a.user,
        customer=customer,
        valid_until=dt.date(2030, 1, 1),
        lines=[{"description": "x", "quantity": Decimal("1"), "unit_price": 100}],
    )
    send_quote(quote, owner_a.user)
    html = client.get(f"/q/{quote.public_token}/").content.decode()
    assert "Vomerani mtengo" in html
    assert "Kanani" in html


def test_customer_language_via_api(client_a):
    res = client_a.post("/api/customers/", {"name": "Mwila", "language": "bem"}, format="json")
    assert res.status_code == 201
    assert res.json()["language"] == "bem"
    bad = client_a.post("/api/customers/", {"name": "X", "language": "fr"}, format="json")
    assert bad.status_code == 400


def test_user_sets_app_language(client_a):
    res = client_a.patch("/api/auth/me/", {"language": "ny"}, format="json")
    assert res.status_code == 200
    assert res.json()["user"]["language"] == "ny"
    assert (
        client_a.patch("/api/auth/me/", {"email": "x@y.z"}, format="json").json()["user"]["email"]
        != "x@y.z"
    )
