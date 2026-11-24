"""Encrypted secrets and plain defaults.

Resolution order for a secret: encrypted row in the database, then the environment.
The UI never receives a value, only whether it is configured, where it came from and
a last-4 hint.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Secret, Setting
from app.security import decrypt, encrypt, hint

HACKER_AI_API_KEY = "HACKER_AI_API_KEY"
ELEVENLABS_API_KEY = "ELEVENLABS_API_KEY"

_ENV = {
    HACKER_AI_API_KEY: lambda: settings.hackerai_api_key,
    ELEVENLABS_API_KEY: lambda: settings.elevenlabs_api_key,
}


def get_secret(db: Session, name: str) -> str:
    row = db.get(Secret, name)
    if row is not None:
        value = decrypt(row.ciphertext)
        if value:
            return value
    if settings.allow_env_secrets:
        return (_ENV.get(name, lambda: "")() or "").strip()
    return ""


def set_secret(db: Session, name: str, value: str) -> None:
    value = (value or "").strip()
    row = db.get(Secret, name)
    if not value:
        if row is not None:
            db.delete(row)
            db.commit()
        return
    if row is None:
        db.add(Secret(name=name, ciphertext=encrypt(value), hint=hint(value)))
    else:
        row.ciphertext = encrypt(value)
        row.hint = hint(value)
    db.commit()


def secret_view(db: Session, name: str) -> dict:
    row = db.get(Secret, name)
    if row is not None:
        value = decrypt(row.ciphertext)
        if value:
            return {"configured": True, "source": "encrypted", "hint": row.hint or hint(value)}
    env_value = (_ENV.get(name, lambda: "")() or "").strip() if settings.allow_env_secrets else ""
    if env_value:
        return {"configured": True, "source": "environment", "hint": hint(env_value)}
    return {"configured": False, "source": "none", "hint": ""}


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(Setting, key)
    if row is None or row.value is None:
        return default
    return row.value


def put_setting(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value or ""))
    else:
        row.value = value or ""
    db.commit()


def effective(db: Session, key: str, default: str) -> str:
    return (get_setting(db, key) or "").strip() or default


def all_settings(db: Session) -> dict[str, str]:
    rows = db.scalars(select(Setting)).all()
    return {row.key: row.value for row in rows}
