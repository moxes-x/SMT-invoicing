"""WhatsApp Business Cloud API client (Phase 2).

One platform-owned WhatsApp Business number sends approved *utility* templates on behalf of each
business; the business name is a template parameter. Configure with WHATSAPP_* settings. If they
aren't set, automatic WhatsApp is simply off and the app keeps using click-to-chat links.

Templates to create and get approved in Meta Business Manager (category: Utility, language en):

  invoice_new       header: DOCUMENT
                    body: "Hello {{1}}, {{2}} has sent you invoice {{3}} for {{4}}, due {{5}}.
                           View it here: {{6}}"
  invoice_reminder  header: DOCUMENT
                    body: "Hello {{1}}, a reminder from {{2}}: invoice {{3}} has {{4}} outstanding
                           and was due {{5}}. View and pay: {{6}}"
  quote_new         header: DOCUMENT
                    body: "Hello {{1}}, {{2}} has sent you quote {{3}} for {{4}}, valid until
                           {{5}}. View it and accept or decline: {{6}}"
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

import httpx
from django.conf import settings

GRAPH = "https://graph.facebook.com"


class WhatsAppError(Exception):
    """A send failed. `retryable` is False for errors that won't fix themselves (bad number…)."""

    def __init__(self, message: str, *, retryable: bool = True, code: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.code = code


# Meta error codes that retrying won't fix: invalid recipient, template issues, re-engagement
# window, recipient not on WhatsApp, etc.
PERMANENT_CODES = {131026, 131047, 131051, 132000, 132001, 132005, 132007, 132012, 132015, 100}


def is_enabled() -> bool:
    return bool(settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID)


def verify_signature(body: bytes, header: str | None) -> bool:
    """Check Meta's X-Hub-Signature-256 (HMAC-SHA256 of the raw body with the app secret)."""
    secret = settings.WHATSAPP_APP_SECRET
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


@dataclass
class Document:
    filename: str
    content: bytes


class Client:
    def __init__(self, http: httpx.Client | None = None) -> None:
        self.base = f"{GRAPH}/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}"
        self.http = http or httpx.Client(timeout=20)
        self.headers = {"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"}

    def _check(self, res: httpx.Response) -> dict[str, Any]:
        try:
            data: dict[str, Any] = res.json()
        except ValueError:
            data = {}
        if res.is_success:
            return data
        err = data.get("error", {}) if isinstance(data, dict) else {}
        code = err.get("code")
        message = err.get("message") or f"WhatsApp API error {res.status_code}"
        retryable = res.status_code >= 500 or res.status_code == 429
        if code in PERMANENT_CODES:
            retryable = False
        raise WhatsAppError(message, retryable=retryable, code=code)

    def upload_document(self, doc: Document) -> str:
        res = self.http.post(
            f"{self.base}/media",
            headers=self.headers,
            data={"messaging_product": "whatsapp", "type": "application/pdf"},
            files={"file": (doc.filename, doc.content, "application/pdf")},
        )
        return str(self._check(res)["id"])

    def send_template(
        self,
        to: str,
        template: str,
        params: list[str],
        document: Document | None = None,
    ) -> str:
        components: list[dict[str, Any]] = []
        if document is not None:
            media_id = self.upload_document(document)
            components.append(
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "document",
                            "document": {"id": media_id, "filename": document.filename},
                        }
                    ],
                }
            )
        components.append(
            {"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}
        )
        payload = {
            "messaging_product": "whatsapp",
            "to": to.lstrip("+"),
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": settings.WHATSAPP_TEMPLATE_LANGUAGE},
                "components": components,
            },
        }
        res = self.http.post(f"{self.base}/messages", headers=self.headers, json=payload)
        return str(self._check(res)["messages"][0]["id"])
