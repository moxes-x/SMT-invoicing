"""Encrypt small secrets (e.g. a business's payment gateway key) before they reach the database."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    key = settings.FIELD_ENCRYPTION_KEY
    if not key:
        # Development fallback: derive from SECRET_KEY. Production sets FIELD_ENCRYPTION_KEY so
        # rotating SECRET_KEY doesn't make stored secrets unreadable.
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode() if value else ""


def decrypt(value: str) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return ""  # key changed; the owner has to paste the secret again
