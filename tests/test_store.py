from __future__ import annotations

from app import store
from app.config import settings


def test_secret_is_encrypted_at_rest_and_never_exposed(db):
    store.set_secret(db, store.HACKER_AI_API_KEY, "sk-test-abcdef1234")

    assert store.get_secret(db, store.HACKER_AI_API_KEY) == "sk-test-abcdef1234"

    row = db.get(store.Secret, store.HACKER_AI_API_KEY)
    assert row is not None
    assert "sk-test" not in row.ciphertext
    assert "abcdef1234" not in row.ciphertext

    view = store.secret_view(db, store.HACKER_AI_API_KEY)
    assert view == {"configured": True, "source": "encrypted", "hint": "…1234"}
    assert "sk-test" not in str(view)


def test_database_secret_wins_and_clearing_falls_back_to_environment(db, monkeypatch):
    monkeypatch.setattr(settings, "hackerai_api_key", "sk-env-9999")

    view = store.secret_view(db, store.HACKER_AI_API_KEY)
    assert view["source"] == "environment"
    assert store.get_secret(db, store.HACKER_AI_API_KEY) == "sk-env-9999"

    store.set_secret(db, store.HACKER_AI_API_KEY, "sk-db-0000")
    assert store.get_secret(db, store.HACKER_AI_API_KEY) == "sk-db-0000"
    assert store.secret_view(db, store.HACKER_AI_API_KEY)["source"] == "encrypted"

    store.set_secret(db, store.HACKER_AI_API_KEY, "")
    assert db.get(store.Secret, store.HACKER_AI_API_KEY) is None
    assert store.get_secret(db, store.HACKER_AI_API_KEY) == "sk-env-9999"


def test_missing_secret_reports_none(db):
    view = store.secret_view(db, store.ELEVENLABS_API_KEY)
    assert view == {"configured": False, "source": "none", "hint": ""}
    assert store.get_secret(db, store.ELEVENLABS_API_KEY) == ""


def test_effective_prefers_stored_setting(db):
    assert store.effective(db, "hacker_ai_model", "auto") == "auto"
    store.put_setting(db, "hacker_ai_model", "kimi-k2.5")
    assert store.effective(db, "hacker_ai_model", "auto") == "kimi-k2.5"
    store.put_setting(db, "hacker_ai_model", "   ")
    assert store.effective(db, "hacker_ai_model", "auto") == "auto"
