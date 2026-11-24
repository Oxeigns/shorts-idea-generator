from __future__ import annotations

import base64

from cryptography.fernet import Fernet

from app import security
from app.config import settings


def test_encrypt_round_trip_does_not_leak_plaintext():
    token = security.encrypt("sk-live-abcdef123456")
    assert token != "sk-live-abcdef123456"
    assert "abcdef123456" not in token
    assert security.decrypt(token) == "sk-live-abcdef123456"


def test_decrypt_rejects_garbage_and_foreign_keys():
    assert security.decrypt("not-a-token") == ""
    assert security.decrypt("") == ""
    foreign = Fernet(base64.urlsafe_b64encode(b"0" * 32)).encrypt(b"secret").decode("ascii")
    assert security.decrypt(foreign) == ""


def test_hint_shows_only_the_last_four():
    assert security.hint("sk-1234567890f7d9") == "…f7d9"
    assert security.hint("") == ""
    assert "1234567890" not in security.hint("sk-1234567890f7d9")


def test_session_round_trip_and_signature_tampering():
    token = security.sign_session("admin")
    assert security.read_session(token) == "admin"

    payload, signature = token.rsplit(".", 1)
    flipped = payload[:-1] + ("A" if payload[-1] != "A" else "B")
    zeros = "0" * len(signature)
    assert security.read_session(f"{flipped}.{signature}") is None
    assert security.read_session(f"{payload}.{zeros}") is None
    assert security.read_session("garbage") is None
    assert security.read_session(None) is None


def test_session_expiry():
    assert security.read_session(security.sign_session("admin", days=-1)) is None


def test_safe_next_blocks_offsite_redirects():
    assert security.safe_next(None) == "/"
    assert security.safe_next("https://evil.example/steal") == "/"
    assert security.safe_next("//evil.example") == "/"
    assert security.safe_next("/history?run=3") == "/history?run=3"


def test_password_and_username_comparison():
    assert security.verify_password(settings.admin_password)
    assert not security.verify_password("wrong-password")
    assert security.verify_username(settings.admin_username)
    assert not security.verify_username("someone-else")
