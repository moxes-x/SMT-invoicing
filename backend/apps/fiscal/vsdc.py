"""Client for ZRA's VSDC (Virtual Sales Data Controller) API, and the sale payloads it takes.

Follows ZRA's "VSDC API Specification" (updated 02-10-2026). The VSDC is a Java service the
taxpayer downloads from the Smart Invoice portal and runs on their own server; it holds the API
keys, so requests carry no credentials. Base URL http://<host>:<port>/<vsdcpath>.

Amounts go in major units of the invoice currency, and line prices include VAT: K100 at 16% is
taxable 86.2069 and VAT 13.7931 (4 decimal places), as in ZRA's examples. Every answer is
{resultCd, resultMsg, resultDt, data}; "000" means success (spec 6.13).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx
from django.utils import timezone

from .models import VAT_RATES, ZraDevice

TIMEOUT = httpx.Timeout(30.0, connect=10.0)
OK = "000"
FOUR = Decimal("0.0001")
TWO = Decimal("0.01")

QTY_UNIT = "U"  # 6.5: Pieces/item [Number]
PKG_UNIT = "NT"  # 6.4: Net
ORIGIN_COUNTRY = "ZM"
CREDIT_REASON = "07"  # 6.15: Other (the reason itself goes in invcAdjustReason)
DUPLICATE = "924"  # 6.13: CIS Invoice number already exists
USER = "SMTINVOICE"


class VsdcError(Exception):
    def __init__(self, message: str, *, code: str = ""):
        super().__init__(message)
        self.code = code


def money(minor: int | Decimal) -> Decimal:
    return (Decimal(minor) / 100).quantize(FOUR, rounding=ROUND_HALF_UP)


def q4(value: Decimal) -> Decimal:
    return value.quantize(FOUR, rounding=ROUND_HALF_UP)


def num(value: Decimal) -> float:
    """JSON number for the VSDC. 4 decimal places is all it keeps."""
    return float(q4(value))


@dataclass
class Line:
    code: str
    name: str  # what the customer sees on this line
    item_name: str  # the name the item code is saved under on the VSDC
    category: str
    quantity: Decimal
    unit_price: int  # minor units, VAT-inclusive
    discount: int  # minor units off the line

    @property
    def supply(self) -> Decimal:
        return q4(self.quantity * money(self.unit_price))

    @property
    def total(self) -> Decimal:
        return q4(self.supply - money(self.discount))

    @property
    def taxable(self) -> Decimal:
        rate = VAT_RATES[self.category]
        return q4(self.total * 100 / (100 + rate)) if rate else self.total

    @property
    def tax(self) -> Decimal:
        return q4(self.total - self.taxable)


def vat_summary(lines: Iterable[Line]) -> list[dict[str, Any]]:
    by_cat: dict[str, list[Decimal]] = {}
    for line in lines:
        taxable, tax = by_cat.setdefault(line.category, [Decimal(0), Decimal(0)])
        by_cat[line.category] = [taxable + line.taxable, tax + line.tax]
    return [
        {"category": c, "rate": VAT_RATES[c], "taxable": str(q4(t)), "tax": str(q4(x))}
        for c, (t, x) in sorted(by_cat.items())
    ]


TAX_KEYS = ["A", "B", "C1", "C2", "C3", "D", "Rvat", "E", "F", "Ipl1", "Ipl2", "Tl", "Ecm", "Exeeg"]
TAX_RATES = {
    "A": 16,
    "B": 16,
    "C1": 0,
    "C2": 0,
    "C3": 0,
    "D": 0,
    "Rvat": 16,
    "E": 0,
    "F": 10,
    "Ipl1": 5,
    "Ipl2": 0,
    "Tl": 1.5,
    "Ecm": 5,
    "Exeeg": 3,
    "Tot": 0,
}


def sale_payload(
    device: ZraDevice,
    *,
    number: str,
    lines: list[Line],
    customer_name: str,
    customer_tpin: str,
    currency: str,
    exchange_rate: Decimal | None,
    sale_date: dt.date,
    total: int,
    credit_for: Any = None,
    reason: str = "",
) -> dict[str, Any]:
    """saveSales body. `credit_for` (a FiscalReceipt) turns it into a credit note for that sale."""
    business = device.business
    taxable = {k: Decimal(0) for k in TAX_KEYS}
    tax = {k: Decimal(0) for k in TAX_KEYS}
    items = []
    for seq, line in enumerate(lines, start=1):
        taxable[line.category] += line.taxable
        tax[line.category] += line.tax
        supply = line.supply
        discount = money(line.discount)
        items.append(
            {
                "itemSeq": seq,
                "itemCd": line.code,
                "itemClsCd": device.item_class_code,
                "itemNm": line.name[:200],
                "bcd": "",
                "pkgUnitCd": PKG_UNIT,
                "pkg": 0,
                "qtyUnitCd": QTY_UNIT,
                "qty": float(line.quantity),
                "prc": num(money(line.unit_price)),
                "splyAmt": num(supply),
                "dcRt": float((discount * 100 / supply).quantize(TWO)) if supply else 0,
                "dcAmt": num(discount),
                "isrccCd": "",
                "isrccNm": "",
                "isrcRt": 0,
                "isrcAmt": 0,
                "vatCatCd": line.category,
                "exciseTxCatCd": None,
                "tlCatCd": None,
                "iplCatCd": None,
                "vatTaxblAmt": num(line.taxable),
                "vatAmt": num(line.tax),
                "exciseTaxblAmt": 0,
                "tlTaxblAmt": 0,
                "iplTaxblAmt": 0,
                "iplAmt": 0,
                "tlAmt": 0,
                "exciseTxAmt": 0,
                "totAmt": num(line.total),
            }
        )
    body: dict[str, Any] = {
        "tpin": business.tpin,
        "bhfId": device.branch_id,
        "orgInvcNo": 0,
        "cisInvcNo": number,
        "custTpin": customer_tpin or None,
        "custNm": customer_name[:60],
        "salesTyCd": "N",
        "rcptTyCd": "S",
        "pmtTyCd": device.payment_type,
        "salesSttsCd": "02",
        "cfmDt": timezone.localtime().strftime("%Y%m%d%H%M%S"),
        "salesDt": sale_date.strftime("%Y%m%d"),
        "stockRlsDt": None,
        "cnclReqDt": None,
        "cnclDt": None,
        "rfdDt": None,
        "rfdRsnCd": None,
        "totItemCnt": len(items),
        **{f"taxblAmt{k}": num(v) for k, v in taxable.items()},
        "taxblAmtTot": 0,
        **{f"taxRt{k}": v for k, v in TAX_RATES.items()},
        **{f"taxAmt{k}": num(v) for k, v in tax.items()},
        "taxAmtTot": 0,
        "totTaxblAmt": num(sum(taxable.values(), Decimal(0))),
        "totTaxAmt": num(sum(tax.values(), Decimal(0))),
        "cashDcRt": 0,
        "cashDcAmt": 0,
        "totAmt": num(money(total)),
        "prchrAcptcYn": "N",
        "remark": "",
        "regrId": USER,
        "regrNm": USER,
        "modrId": USER,
        "modrNm": USER,
        "saleCtyCd": "1",
        "lpoNumber": None,
        "currencyTyCd": currency,
        "exchangeRt": str(exchange_rate if currency != "ZMW" and exchange_rate else 1),
        "destnCountryCd": "",
        "dbtRsnCd": "",
        "invcAdjustReason": "",
        "itemList": items,
    }
    if credit_for is not None:
        reason = (reason or "Invoice cancelled")[:100]
        body.update(
            rcptTyCd="R",
            orgSdcId=credit_for.sdc_id,
            orgInvcNo=int(credit_for.receipt_no) if credit_for.receipt_no.isdigit() else 0,
            rfdDt=body["cfmDt"],
            rfdRsnCd=CREDIT_REASON,
            dbtRsnCd=None,
            invcAdjustReason=reason,
            remark=reason,
        )
    return body


def item_payload(device: ZraDevice, line: Line) -> dict[str, Any]:
    return {
        "tpin": device.business.tpin,
        "bhfId": device.branch_id,
        "itemCd": line.code,
        "itemClsCd": device.item_class_code,
        "itemTyCd": device.item_type,
        "itemNm": line.item_name[:200],
        "itemStdNm": line.item_name[:200],
        "orgnNatCd": ORIGIN_COUNTRY,
        "pkgUnitCd": PKG_UNIT,
        "qtyUnitCd": QTY_UNIT,
        "vatCatCd": line.category,
        "iplCatCd": None,
        "tlCatCd": None,
        "exciseTxCatCd": None,
        "btchNo": None,
        "bcd": None,
        "dftPrc": num(money(line.unit_price)),
        "manufacturerTpin": None,
        "manufacturerItemCd": None,
        "rrp": None,
        "svcChargeYn": "N",
        "rentalYn": "N",
        "addInfo": None,
        "sftyQty": 0,
        "isrcAplcbYn": "N",
        "useYn": "Y",
        "regrNm": USER,
        "regrId": USER,
        "modrNm": USER,
        "modrId": USER,
    }


class Client:
    def __init__(self, device: ZraDevice):
        self.device = device

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = self.device.vsdc_url.rstrip("/") + path
        try:
            with httpx.Client(timeout=TIMEOUT) as http:
                res = http.post(url, json=body)
        except httpx.HTTPError as exc:
            raise VsdcError(f"Couldn't reach the ZRA VSDC at {self.device.vsdc_url}.") from exc
        try:
            answer = res.json()
        except ValueError:
            answer = None
        if not isinstance(answer, dict):
            raise VsdcError(f"The VSDC sent an unexpected answer (HTTP {res.status_code}).")
        code = str(answer.get("resultCd", ""))
        if code != OK:
            message = answer.get("resultMsg") or f"HTTP {res.status_code}"
            raise VsdcError(f"ZRA said: {str(message)[:250]} (code {code or '?'})", code=code)
        return answer

    def init_info(self) -> dict[str, Any]:
        """Device initialisation (selectInitInfo): checks the TPIN, branch and serial."""
        return self.post(
            "/initializer/selectInitInfo",
            {
                "tpin": self.device.business.tpin,
                "bhfId": self.device.branch_id,
                "dvcSrlNo": self.device.device_serial,
            },
        )

    def save_item(self, body: dict[str, Any], *, update: bool = False) -> dict[str, Any]:
        return self.post("/items/updateItem" if update else "/items/saveItem", body)

    def save_sale(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.post("/trnsSales/saveSales", body)

    def select_invoice(self, number: str) -> dict[str, Any]:
        return self.post(
            "/trnsSales/selectInvoice",
            {
                "tpin": self.device.business.tpin,
                "bhfId": self.device.branch_id,
                "invcSdcId": self.device.sdc_id,
                "cisInvcNo": number,
            },
        )


def receipt_fields(answer: dict[str, Any]) -> dict[str, str]:
    """The signed receipt from a saveSales or selectInvoice answer (spec 5.9)."""
    data = answer.get("data") or {}
    if not isinstance(data, dict):
        data = {}

    def pick(*names: str) -> str:
        for name in names:
            if data.get(name) not in (None, ""):
                return str(data[name])
        return ""

    return {
        "receipt_no": pick("rcptNo", "invcNo", "curRcptNo"),
        "sdc_id": pick("sdcId", "invcSdcId"),
        "mrc_no": pick("mrcNo"),
        "internal_data": pick("intrlData"),
        "signature": pick("rcptSign"),
        "qr_url": pick("qrCodeUrl", "qrCode"),
        "signed_at": pick("vsdcRcptPbctDate", "rcptPbctDt"),
    }


def init_fields(answer: dict[str, Any]) -> dict[str, str]:
    """sdcId and mrcNo from the selectInitInfo answer (data.info, spec 5.1)."""
    data = answer.get("data") or {}
    info = data.get("info", data) if isinstance(data, dict) else {}
    if not isinstance(info, dict):
        info = {}
    return {"sdc_id": str(info.get("sdcId") or ""), "mrc_no": str(info.get("mrcNo") or "")}
