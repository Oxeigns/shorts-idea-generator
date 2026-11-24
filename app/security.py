"""Encryption for stored API keys and signed session cookies.

Secrets are encrypted at rest with Fernet derived from APP_SECRET_KEY. Only a last-4
hint is ever sent to the browser.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def hint(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    return "…" + cleaned[-4:]


def _sign(payload: str) -> str:
    return hmac.new(settings.secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def sign_session(username: str, days: int | None = None) -> str:
    expires = int(time.time()) + (days or settings.session_days) * 86400
    payload = base64.urlsafe_b64encode(json.dumps({"u": username, "exp": expires}).encode("utf-8")).decode("ascii")
    return f"{payload}.{_sign(payload)}"


def read_session(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    payload, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except Exception:  # noqa: BLE001
        return None
    if int(data.get("exp") or 0) < int(time.time()):
        return None
    return str(data.get("u") or "") or None


def verify_password(candidate: str) -> bool:
    return hmac.compare_digest((candidate or "").encode("utf-8"), settings.admin_password.encode("utf-8"))


def verify_username(candidate: str) -> bool:
    return hmac.compare_digest((candidate or "").strip().encode("utf-8"), settings.admin_username.encode("utf-8"))


def safe_next(target: str | None) -> str:
    """Only allow same-origin relative redirects after login."""
    if not target:
        return "/"
    if not target.startswith("/") or target.startswith("//"):
        return "/"
    return quote(target, safe="/?=&%")
