"""Regression tests for the audit fixes and the hardening layer.

Covers: search past the old 200-row page limit, real voiceover counts,
deterministic newest-voiceover selection, delete semantics, provider retries,
base-URL validation, rate limiting, CSP headers and the no-inline-asset rule.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app import netguard
from app.main import reset_rate_limits
from app.models import Idea, Run, Voiceover
from app.services import hackerai
from app.services import ideas as service
from app.timeutil import utcnow
from tests.helpers import valid_idea

TEMPLATES = Path(__file__).resolve().parent.parent / "app" / "templates"


def make_run(db, requested: int = 10) -> Run:
    run = Run(
        categories_json=json.dumps(hackerai.CATEGORIES),
        auto=True,
        requested=requested,
        status="running",
        model="auto",
        created_at=utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def store_idea(db, run: Run, index: int = 1) -> Idea:
    idea = service._save_idea(db, run, valid_idea(index), "auto")
    db.commit()
    db.refresh(idea)
    return idea


# ------------------------------------------------------------------- search
def test_search_reaches_rows_beyond_the_old_limit(db):
    """Before the fix, list_ideas limited to 200 rows, then filtered in Python."""
    run = make_run(db, 201)
    for index in range(201):
        service._save_idea(db, run, valid_idea((index % 12) + 1), "auto")
    db.commit()

    oldest = db.scalar(select(Idea).order_by(Idea.id.asc()))
    assert oldest is not None
    oldest.title = "Ancient temple secret of the sea"
    db.commit()

    rows = service.list_ideas(db, query="ancient temple")
    assert [row.id for row in rows] == [oldest.id]
    assert service.list_ideas(db, query="no-such-phrase-anywhere") == []


def test_search_is_case_insensitive_across_fields(db):
    run = make_run(db, 1)
    idea = store_idea(db, run)
    idea.description = "A hidden OCEAN fact"
    idea.hashtags_json = json.dumps(["#DeepSea"])
    db.commit()

    assert [row.id for row in service.list_ideas(db, query="ocean")] == [idea.id]
    assert [row.id for row in service.list_ideas(db, query="deepsea")] == [idea.id]


# --------------------------------------------------------------- voiceovers
def test_voiceover_stats_count_voiceovers_not_ideas(db):
    run = make_run(db, 3)
    first = store_idea(db, run, 1)
    second = store_idea(db, run, 2)
    db.add(Voiceover(idea_id=first.id, status="ready", path="/tmp/one.mp3", chars=10))
    db.add(Voiceover(idea_id=second.id, status="failed", path="", error="402"))
    db.commit()

    stats = service.stats(db)
    assert stats["total"] == 2
    assert stats["voiceovers"] == 1


def test_latest_voiceover_is_the_highest_id_ready_row(db, tmp_path):
    run = make_run(db, 1)
    idea = store_idea(db, run)
    older = Voiceover(idea_id=idea.id, status="ready", path=str(tmp_path / "old.mp3"), chars=10)
    newer = Voiceover(idea_id=idea.id, status="ready", path=str(tmp_path / "new.mp3"), chars=12)
    failed = Voiceover(idea_id=idea.id, status="failed", path="", error="402")
    db.add_all([older, newer, failed])
    db.commit()

    db.expire_all()
    reloaded = db.get(Idea, idea.id)
    assert reloaded is not None
    assert [item.id for item in reloaded.voiceovers] == sorted(item.id for item in reloaded.voiceovers)
    assert reloaded.latest_voiceover is not None
    assert reloaded.latest_voiceover.id == newer.id
    payload = reloaded.as_dict()
    assert payload["voiceover_url"] == f"/voice/{newer.id}.mp3"
    assert payload["voiceover_download"] == f"/voice/{newer.id}/download"


# ------------------------------------------------------------------- delete
def test_delete_idea_removes_audio_and_hides_row(db, tmp_path):
    run = make_run(db, 1)
    idea = store_idea(db, run)
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"ID3fake")
    db.add(Voiceover(idea_id=idea.id, status="ready", path=str(audio), chars=4))
    db.commit()

    removed = service.delete_idea(db, idea.id)
    assert removed == 1
    assert not audio.exists()

    db.expire_all()
    stored = db.get(Idea, idea.id)
    assert stored is not None and stored.status == "deleted"
    assert service.list_ideas(db) == []
    assert service.stats(db)["total"] == 0

    with pytest.raises(ValueError):
        service.delete_idea(db, idea.id)


def test_delete_endpoint_requires_auth(client, db):
    run = make_run(db, 1)
    idea = store_idea(db, run)

    anonymous = client.delete(f"/api/ideas/{idea.id}")
    assert anonymous.status_code == 401


def test_delete_endpoint_works_when_signed_in(auth_client, db):
    run = make_run(db, 1)
    idea = store_idea(db, run)

    response = auth_client.delete(f"/api/ideas/{idea.id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True and body["deleted"] == idea.id

    again = auth_client.delete(f"/api/ideas/{idea.id}")
    assert again.status_code == 404


# ------------------------------------------------------------------- retries
def _response(status: int, retry_after: str | None = None) -> httpx.Response:
    headers = {"retry-after": retry_after} if retry_after else {}
    request = httpx.Request("POST", "https://api.hackerai.sh/v1/chat/completions")
    return httpx.Response(status, headers=headers, request=request)


def test_hackerai_retries_transient_failures(monkeypatch):
    calls: list[int] = []
    sleeps: list[float] = []
    replies = [_response(500), _response(429, retry_after="2"), _response(200)]

    def fake_send(url, headers, payload, timeout):
        calls.append(1)
        return replies.pop(0)

    monkeypatch.setattr(hackerai, "_send", fake_send)
    monkeypatch.setattr(hackerai, "_sleep", lambda seconds: sleeps.append(seconds))

    response = hackerai._post("https://api.hackerai.sh/v1/chat/completions", {}, {}, 5)
    assert response.status_code == 200
    assert len(calls) == 3
    assert sleeps[0] < 2.0  # first 500 uses exponential backoff
    assert sleeps[1] == 2.0  # Retry-After honoured


def test_hackerai_returns_the_final_5xx_after_max_attempts(monkeypatch):
    calls = []

    def fake_send(*args):
        calls.append(1)
        return _response(503)

    monkeypatch.setattr(hackerai, "_send", fake_send)
    monkeypatch.setattr(hackerai, "_sleep", lambda seconds: None)

    response = hackerai._post("https://api.hackerai.sh/v1/chat/completions", {}, {}, 5)
    assert response.status_code == 503
    assert len(calls) == hackerai.MAX_ATTEMPTS


def test_hackerai_does_not_retry_a_client_error(monkeypatch):
    calls = []

    def fake_send(*args):
        calls.append(1)
        return _response(400)

    monkeypatch.setattr(hackerai, "_send", fake_send)
    response = hackerai._post("https://api.hackerai.sh/v1/chat/completions", {}, {}, 5)
    assert response.status_code == 400
    assert len(calls) == 1


# --------------------------------------------------------------- base URL
@pytest.mark.parametrize(
    "value",
    [
        "http://api.hackerai.sh/v1",
        "ftp://api.hackerai.sh",
        "https://127.0.0.1/v1",
        "https://localhost/v1",
        "https://user:pass@api.hackerai.sh/v1",
        "https://api.hackerai.sh/v1?redirect=evil",
        "https://10.0.0.5/v1",
        "https://169.254.169.254/latest",
    ],
)
def test_netguard_rejects_unsafe_base_urls(value):
    with pytest.raises(netguard.InvalidBaseURL):
        netguard.validate_base_url(value)


def test_netguard_normalises_an_https_url():
    assert netguard.validate_base_url(" https://api.hackerai.sh/v1/ ") == "https://api.hackerai.sh/v1"


def test_config_rejects_a_private_base_url(auth_client):
    response = auth_client.post(
        "/config",
        data={"hacker_ai_base_url": "http://127.0.0.1:8080"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/config?error=" in response.headers["location"]

    saved = auth_client.post(
        "/config",
        data={"hacker_ai_base_url": "https://api.hackerai.sh/v1"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert saved.headers["location"] == "/config?saved=1"


# -------------------------------------------------------------- rate limits
def test_generate_is_rate_limited(auth_client):
    reset_rate_limits()
    try:
        statuses = []
        for _ in range(7):
            response = auth_client.post(
                "/api/ideas/generate", json={"count": 10, "categories": [], "auto": True}
            )
            statuses.append(response.status_code)
        assert statuses[:6] == [400] * 6, statuses
        assert statuses[6] == 429, statuses

        limited = auth_client.post(
            "/api/ideas/generate", json={"count": 10, "categories": [], "auto": True}
        )
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) > 0
        assert "Too many requests" in limited.json()["detail"]
    finally:
        reset_rate_limits()


# ---------------------------------------------------------- security headers
def test_security_headers_are_strict(client):
    response = client.get("/login")
    csp = response.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_templates_contain_no_inline_style_or_handlers():
    import re

    for template in TEMPLATES.glob("*.html"):
        text = template.read_text(encoding="utf-8")
        assert not re.search(r"\sstyle\s*=", text), f"inline style in {template.name}"
        assert not re.search(r"\son[a-z]+\s*=", text), f"inline handler in {template.name}"
        assert not re.search(r"<script(?![^>]*\bsrc=)", text), f"inline script in {template.name}"


def test_theme_cookie_is_reflected_server_side(client):
    client.cookies.set("theme", "light")
    response = client.get("/login")
    assert 'data-theme="light"' in response.text
