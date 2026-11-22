"""Lenco (BroadPay) collections API client.

Docs: https://lenco-api.readme.io/v2.0/reference. Amounts go to Lenco in major units (K12.50 →
12.5); we keep ngwee everywhere else. Lenco answers HTTP 200 even when a collection fails, so the
`data.status` field is what matters.
"""

from __future__ import annotations

import hashlib
import hmac
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx

from .models import LencoAccount

TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class LencoError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def to_major(ngwee: int) -> float:
    return float(Decimal(ngwee) / 100)


def to_minor(amount: str | float | int | None) -> int:
    return int((Decimal(str(amount or 0)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def local_phone(e164: str) -> str:
    """Lenco's examples use the local form: +260961234567 → 0961234567."""
    digits = "".join(c for c in e164 if c.isdigit())
    if digits.startswith("260") and len(digits) == 12:
        return "0" + digits[3:]
    return digits


def guess_operator(e164: str) -> str:
    """Zambian prefixes: 096/076 MTN, 097/077 Airtel, 095/075 Zamtel."""
    local = local_phone(e164)
    return (
        {"6": "mtn", "7": "airtel", "5": "zamtel"}.get(local[2:3], "") if len(local) == 10 else ""
    )


def verify_signature(account: LencoAccount, body: bytes, header: str) -> bool:
    if not header or not account.secret_key:
        return False
    expected = hmac.new(account.webhook_hash_key.encode(), body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, header.strip().lower())


class Client:
    def __init__(self, account: LencoAccount):
        self.account = account

    def _request(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.account.secret_key}",
            "Accept": "application/json",
        }
        try:
            with httpx.Client(timeout=TIMEOUT) as http:
                res = http.request(method, self.account.api_url + path, headers=headers, **kw)
        except httpx.HTTPError as exc:
            raise LencoError(f"Couldn't reach Lenco: {exc}") from exc
        try:
            body = res.json()
        except ValueError:
            body = {}
        if res.status_code >= 400 or not body.get("status", False):
            message = body.get("message") or f"Lenco returned HTTP {res.status_code}"
            raise LencoError(str(message)[:300], status_code=res.status_code)
        data = body.get("data")
        if not isinstance(data, dict):
            raise LencoError("Lenco sent an unexpected response.")
        return data

    def collect_mobile_money(
        self, *, reference: str, amount: int, phone: str, operator: str
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/collections/mobile-money",
            json={
                "reference": reference,
                "amount": to_major(amount),
                "phone": local_phone(phone),
                "operator": operator,
                "country": "zm",
                "bearer": "merchant",
            },
        )

    def collection_status(self, reference: str) -> dict[str, Any]:
        return self._request("GET", f"/collections/status/{reference}")
