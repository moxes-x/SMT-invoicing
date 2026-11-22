from decimal import Decimal

import pytest

from apps.fiscal import vsdc
from apps.fiscal.models import FiscalReceipt, ZraDevice
from apps.invoices.models import Invoice
from apps.invoices.services import send_invoice

from .factories import CustomerFactory, ItemFactory, MembershipFactory, make_invoice


def line(description="Bread", quantity="1", unit_price=10000, discount=0, **kw):
    return {
        "description": description,
        "quantity": Decimal(quantity),
        "unit_price": unit_price,
        "discount": discount,
        **kw,
    }


class TestAmounts:
    def make(self, category="A", quantity="1", unit_price=10000, discount=0):
        return vsdc.Line(
            code="X",
            name="X",
            item_name="X",
            category=category,
            quantity=Decimal(quantity),
            unit_price=unit_price,
            discount=discount,
        )

    def test_prices_include_vat_like_zras_example(self):
        # ZRA's own example: K100 at 16% → taxable 86.2069, VAT 13.7931
        line = self.make()
        assert (line.total, line.taxable, line.tax) == (
            Decimal("100.0000"),
            Decimal("86.2069"),
            Decimal("13.7931"),
        )

    def test_zero_rated_and_exempt_have_no_vat(self):
        for cat in ("C1", "C2", "C3", "D"):
            line = self.make(category=cat, quantity="4")
            assert (line.taxable, line.tax) == (Decimal("400.0000"), Decimal("0.0000"))

    def test_discount_comes_off_before_vat(self):
        line = self.make(unit_price=12500, discount=2500)
        assert line.supply == Decimal("125.0000")
        assert line.total == Decimal("100.0000")
        assert line.taxable == Decimal("86.2069")

    def test_vat_summary_groups_by_category(self):
        rows = vsdc.vat_summary([self.make(), self.make(), self.make("D")])
        assert rows == [
            {"category": "A", "rate": 16, "taxable": "172.4138", "tax": "27.5862"},
            {"category": "D", "rate": 0, "taxable": "100.0000", "tax": "0.0000"},
        ]


@pytest.mark.django_db
class TestSendingATaxInvoice:
    def test_send_reports_the_sale_and_keeps_the_signed_receipt(
        self, owner_a, vsdc_api, zra_device
    ):
        business = owner_a.business
        bread = ItemFactory(business=business, name="Bread", vat_category="A")
        customer = CustomerFactory(business=business, name="Lusaka Lodge", tpin="2000000000")
        invoice = make_invoice(
            business,
            customer=customer,
            lines=[
                line(item=bread, quantity="2", unit_price=12500, discount=5000),
                line("Delivery", unit_price=5000),
            ],
            send=True,
        )
        assert invoice.status == Invoice.Status.SENT
        sale = vsdc_api.calls("/trnsSales/saveSales")[0]
        assert sale["tpin"] == "1000000000" and sale["bhfId"] == "000"
        assert sale["cisInvcNo"] == invoice.number and sale["rcptTyCd"] == "S"
        assert sale["custTpin"] == "2000000000" and sale["custNm"] == "Lusaka Lodge"
        assert sale["salesDt"] == "20261101" and sale["currencyTyCd"] == "ZMW"
        assert sale["totItemCnt"] == 2 and sale["totAmt"] == 250.0
        assert sale["taxblAmtA"] == 215.5172 and sale["taxAmtA"] == 34.4828
        first = sale["itemList"][0]
        assert first["itemCd"] == f"ZM3NTU{bread.pk:07d}" and first["itemClsCd"] == "50102518"
        assert (first["qty"], first["prc"], first["splyAmt"], first["dcAmt"]) == (
            2.0,
            125.0,
            250.0,
            50.0,
        )
        assert first["dcRt"] == 20.0 and first["totAmt"] == 200.0
        assert sale["itemList"][1]["itemCd"] == "ZM3NTU9900001"
        # each item code is saved on the VSDC once
        saved = vsdc_api.calls("/items/saveItem")
        assert [b["itemCd"] for b in saved] == [f"ZM3NTU{bread.pk:07d}", "ZM3NTU9900001"]
        assert saved[0]["itemTyCd"] == "3" and saved[0]["itemNm"] == "Bread"
        receipt = invoice.fiscal_receipts.get()
        assert receipt.kind == "sale" and receipt.receipt_no == "101"
        assert receipt.signature == f"SIGN{invoice.number}"
        assert receipt.qr_url.endswith("r=101")
        assert receipt.tax_total == Decimal("34.4828")
        assert list(invoice.lines.values_list("vat_category", flat=True)) == ["A", "A"]

        make_invoice(business, customer=customer, lines=[line(item=bread)], send=True)
        assert len(vsdc_api.calls("/items/saveItem")) == 2

    def test_category_falls_back_to_the_business_default(self, owner_a, vsdc_api, zra_device):
        zra_device.default_vat_category = "D"
        zra_device.save()
        make_invoice(owner_a.business, lines=[line()], send=True)
        sale = vsdc_api.calls("/trnsSales/saveSales")[0]
        assert sale["itemList"][0]["vatCatCd"] == "D"
        assert sale["taxblAmtD"] == 100.0 and sale["totTaxAmt"] == 0.0

    def test_zra_refusing_keeps_the_invoice_a_draft(self, owner_a, vsdc_api, zra_device, client_a):
        invoice = make_invoice(owner_a.business)
        vsdc_api.fail["/trnsSales/saveSales"] = ("910", "Invalid TPIN")
        res = client_a.post(f"/api/invoices/{invoice.pk}/send/", {}, format="json")
        assert res.status_code == 400
        assert "Invalid TPIN" in res.json()["detail"]
        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.DRAFT
        assert not FiscalReceipt.objects.exists()
        # Trying again works, and doesn't trip over the item it saved the first time
        vsdc_api.fail["/items/saveItem"] = ("921", "Already exists")
        res = client_a.post(f"/api/invoices/{invoice.pk}/send/", {}, format="json")
        assert res.status_code == 200, res.content
        assert res.json()["fiscal_receipts"][0]["receipt_no"] == "101"
        assert [p for p, _ in vsdc_api.requests if "Item" in p] == [
            "/items/saveItem",
            "/items/saveItem",
            "/items/updateItem",
        ]

    def test_number_zra_already_has_fetches_the_signed_receipt(self, owner_a, vsdc_api, zra_device):
        invoice = make_invoice(owner_a.business)
        vsdc_api.fail["/trnsSales/saveSales"] = ("924", "CIS Invoice number already exists.")
        send_invoice(invoice, owner_a.user)
        lookup = vsdc_api.calls("/trnsSales/selectInvoice")[0]
        assert lookup["cisInvcNo"] == invoice.number and lookup["invcSdcId"] == "SDC0010000001"
        assert invoice.fiscal_receipts.get().signature == f"SIGN{invoice.number}"

    def test_vsdc_down_is_a_clear_error(self, owner_a, monkeypatch, zra_device):
        import httpx

        def down(request):
            raise httpx.ConnectError("refused")

        real = httpx.Client
        monkeypatch.setattr(
            "apps.fiscal.vsdc.httpx.Client", lambda **kw: real(transport=httpx.MockTransport(down))
        )
        invoice = make_invoice(owner_a.business)
        with pytest.raises(Exception, match="Couldn't reach the ZRA VSDC"):
            send_invoice(invoice, owner_a.user)
        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.DRAFT

    def test_foreign_currency_needs_a_rate(self, owner_a, vsdc_api, zra_device):
        invoice = make_invoice(owner_a.business, currency="USD")
        with pytest.raises(Exception, match="exchange rate"):
            send_invoice(invoice, owner_a.user)
        invoice.exchange_rate = Decimal("25.5")
        invoice.save()
        send_invoice(invoice, owner_a.user)
        sale = vsdc_api.calls("/trnsSales/saveSales")[0]
        assert (sale["currencyTyCd"], sale["exchangeRt"]) == ("USD", "25.5000")

    def test_rate_is_locked_once_reported(self, owner_a, vsdc_api, zra_device, client_a):
        invoice = make_invoice(
            owner_a.business, currency="USD", exchange_rate=Decimal("25"), send=True
        )
        res = client_a.post(
            f"/api/invoices/{invoice.pk}/exchange-rate/", {"exchange_rate": "26"}, format="json"
        )
        assert res.status_code == 400

    def test_not_vat_registered_or_switched_off_sends_a_plain_invoice(self, owner_a, vsdc_api):
        business = owner_a.business
        ZraDevice.objects.create(business=business, enabled=True, device_serial="1")
        make_invoice(business, send=True)  # not VAT-registered: ignored
        business.vat_registered = True
        business.save()
        ZraDevice.objects.filter(business=business).update(enabled=False)
        make_invoice(business, send=True)
        assert vsdc_api.requests == []
        assert not FiscalReceipt.objects.exists()

    def test_switched_on_but_not_set_up_blocks_sending(self, owner_a, vsdc_api, zra_device):
        zra_device.item_class_code = ""
        zra_device.save()
        invoice = make_invoice(owner_a.business)
        with pytest.raises(Exception, match="not set up"):
            send_invoice(invoice, owner_a.user)

    def test_sending_twice_reports_once(self, owner_a, vsdc_api, zra_device):
        invoice = make_invoice(owner_a.business, send=True)
        send_invoice(invoice, owner_a.user)
        assert len(vsdc_api.calls("/trnsSales/saveSales")) == 1


@pytest.mark.django_db
class TestVoiding:
    def test_void_sends_a_credit_note_for_the_sale(self, owner_a, vsdc_api, zra_device, client_a):
        invoice = make_invoice(owner_a.business, send=True)
        res = client_a.post(
            f"/api/invoices/{invoice.pk}/void/", {"reason": "Wrong customer"}, format="json"
        )
        assert res.status_code == 200, res.content
        credit = vsdc_api.calls("/trnsSales/saveSales")[1]
        assert credit["rcptTyCd"] == "R"
        assert credit["orgInvcNo"] == 101 and credit["orgSdcId"] == "SDC0010000001"
        assert credit["cisInvcNo"].startswith("CN-") and credit["totAmt"] == 500.0
        assert credit["invcAdjustReason"] == "Wrong customer"
        assert credit["rfdRsnCd"] == "07" and credit["rfdDt"] == credit["cfmDt"]
        kinds = [r["kind"] for r in res.json()["fiscal_receipts"]]
        assert kinds == ["sale", "credit"]

    def test_zra_refusing_the_credit_note_keeps_the_invoice(self, owner_a, vsdc_api, zra_device):
        from apps.invoices.services import void_invoice

        invoice = make_invoice(owner_a.business, send=True)
        vsdc_api.fail["/trnsSales/saveSales"] = ("999", "Busy")
        with pytest.raises(Exception, match="Busy"):
            void_invoice(invoice, owner_a.user)
        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.SENT

    def test_reissue_credits_the_old_one_and_reports_the_new_one(
        self, owner_a, vsdc_api, zra_device
    ):
        from apps.invoices.services import reissue_invoice

        invoice = make_invoice(owner_a.business, send=True)
        copy = reissue_invoice(invoice, owner_a.user, "Price change")
        assert invoice.fiscal_receipts.count() == 2
        send_invoice(copy, owner_a.user)
        sales = vsdc_api.calls("/trnsSales/saveSales")
        assert [s["rcptTyCd"] for s in sales] == ["S", "R", "S"]
        assert sales[2]["cisInvcNo"] == copy.number

    def test_plain_invoices_void_without_zra(self, owner_a, vsdc_api, zra_device):
        from apps.invoices.services import void_invoice

        zra_device.enabled = False
        zra_device.save()
        invoice = make_invoice(owner_a.business, send=True)
        void_invoice(invoice, owner_a.user)
        assert vsdc_api.requests == []


@pytest.mark.django_db
class TestDocument:
    def test_only_fiscalised_invoices_say_tax_invoice(self, owner_a, vsdc_api, zra_device, client):
        plain = make_invoice(owner_a.business, send=False)
        zra_device.enabled = False
        zra_device.save()
        send_invoice(plain, owner_a.user)
        html = client.get(plain.public_path).content.decode()
        assert "Tax Invoice" not in html and "not a tax invoice" in html

        zra_device.enabled = True
        zra_device.save()
        taxed = make_invoice(owner_a.business, send=True)
        html = client.get(taxed.public_path).content.decode()
        assert "<h1>Tax Invoice</h1>" in html
        assert "SDC0010000001" in html and f"SIGN{taxed.number}" in html
        assert "VAT summary" in html and "K68.97" in html  # 500 × 16/116
        assert "<svg" in html  # the verification QR
        assert "1 Nov 2026, 12:00" in html

    def test_pdf_renders(self, owner_a, vsdc_api, zra_device, client):
        taxed = make_invoice(owner_a.business, send=True)
        res = client.get(taxed.public_path + "pdf/")
        assert res.status_code == 200 and res["Content-Type"] == "application/pdf"


@pytest.mark.django_db
class TestSettingsApi:
    def test_get_and_save(self, client_a, owner_a):
        res = client_a.get("/api/zra/")
        assert res.status_code == 200
        body = res.json()
        assert body["enabled"] is False and body["vat_registered"] is False
        res = client_a.put(
            "/api/zra/",
            {"device_serial": "20180520000000", "item_class_code": "50102518", "branch_id": "001"},
            format="json",
        )
        assert res.status_code == 200, res.content
        assert res.json()["branch_id"] == "001"

    def test_switching_on_needs_vat_registration_tpin_and_setup(self, client_a, owner_a):
        res = client_a.put("/api/zra/", {"enabled": True}, format="json")
        assert res.status_code == 400 and "VAT-registered" in str(res.json())
        business = owner_a.business
        business.vat_registered = True
        business.save()
        res = client_a.put("/api/zra/", {"enabled": True}, format="json")
        assert "TPIN" in str(res.json())
        business.tpin = "1000000000"
        business.save()
        res = client_a.put("/api/zra/", {"enabled": True}, format="json")
        assert "device_serial" in res.json()
        res = client_a.put(
            "/api/zra/",
            {"enabled": True, "device_serial": "2018", "item_class_code": "50102518"},
            format="json",
        )
        assert res.status_code == 200 and res.json()["is_ready"] is True

    def test_bad_branch_id(self, client_a):
        res = client_a.put("/api/zra/", {"branch_id": "1"}, format="json")
        assert res.status_code == 400

    def test_test_connection_initialises_the_device(self, client_a, vsdc_api, zra_device):
        zra_device.sdc_id = ""
        zra_device.save()
        res = client_a.post("/api/zra/test/")
        assert res.json() == {
            "ok": True,
            "message": "Connected to the ZRA VSDC. SDC ID SDC0010000001.",
        }
        init = vsdc_api.calls("/initializer/selectInitInfo")[0]
        assert init == {"tpin": "1000000000", "bhfId": "000", "dvcSrlNo": "20180520000000"}
        zra_device.refresh_from_db()
        assert zra_device.sdc_id == "SDC0010000001" and zra_device.initialized_at

    def test_test_connection_reports_zra_errors(self, client_a, vsdc_api, zra_device):
        vsdc_api.fail["/initializer/selectInitInfo"] = ("901", "This device is not valid")
        res = client_a.post("/api/zra/test/")
        assert res.json()["ok"] is False and "not valid" in res.json()["message"]

    def test_only_managers_change_it(self, owner_a, zra_device):
        from rest_framework.test import APIClient

        staff = MembershipFactory(business=owner_a.business, role="staff")
        client = APIClient()
        client.force_login(staff.user)
        assert client.get("/api/zra/").status_code == 200
        assert client.put("/api/zra/", {"branch_id": "002"}, format="json").status_code == 403
        assert client.post("/api/zra/test/").status_code == 403

    def test_items_and_customers_take_zra_fields(self, client_a):
        res = client_a.post(
            "/api/items/",
            {"name": "Export maize", "unit_price": 1000, "vat_category": "C1"},
            format="json",
        )
        assert res.status_code == 201 and res.json()["vat_category"] == "C1"
        res = client_a.post("/api/customers/", {"name": "Acme", "tpin": "123"}, format="json")
        assert res.status_code == 400 and "tpin" in res.json()
        res = client_a.post(
            "/api/customers/", {"name": "Acme", "tpin": "2000000000"}, format="json"
        )
        assert res.status_code == 201 and res.json()["tpin"] == "2000000000"


def test_receipt_fields_are_read_defensively():
    assert vsdc.receipt_fields({"resultCd": "000"})["receipt_no"] == ""
    fields = vsdc.receipt_fields({"data": {"invcNo": 7, "invcSdcId": "SDC9", "qrCode": "q"}})
    assert (fields["receipt_no"], fields["sdc_id"], fields["qr_url"]) == ("7", "SDC9", "q")
    assert vsdc.init_fields({"data": {"sdcId": "S", "mrcNo": "M"}}) == {
        "sdc_id": "S",
        "mrc_no": "M",
    }


def test_vsdc_time():
    from apps.fiscal.templatetags.fiscal import vsdc_time

    assert vsdc_time("20240508194441") == "8 May 2024, 19:44"
    assert vsdc_time("2024-06-13 18:46:20") == "13 Jun 2024, 18:46"
    assert vsdc_time("soon") == "soon"
