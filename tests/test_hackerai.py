from __future__ import annotations

import json

import pytest

from app.services import hackerai
from tests.helpers import HINDI_SCRIPT, LATIN_SCRIPT, raw_idea


# --------------------------------------------------------------------- validation
def test_complete_idea_is_accepted():
    idea, reason = hackerai.normalise_idea(raw_idea(), ["Mystery"])
    assert reason == ""
    assert idea is not None
    assert idea["title"].startswith("समुद्र")
    assert idea["category"] == "Mystery"
    assert idea["emotion"] == "mysterious"
    assert idea["duration_sec"] == 45
    assert idea["voiceover_text"] == HINDI_SCRIPT


def test_latin_only_script_is_rejected():
    idea, reason = hackerai.normalise_idea(raw_idea(script=LATIN_SCRIPT), ["Mystery"])
    assert idea is None
    assert "Devanagari" in reason


def test_short_script_is_rejected():
    idea, reason = hackerai.normalise_idea(raw_idea(script="बहुत छोटा"), ["Mystery"])
    assert idea is None
    assert "too short" in reason


def test_missing_scenes_are_rejected():
    idea, reason = hackerai.normalise_idea(raw_idea(scenes=[{"scene": 1, "visual": "एक" * 40}]), ["Mystery"])
    assert idea is None
    assert "scenes" in reason


def test_missing_subtitles_are_rejected():
    idea, reason = hackerai.normalise_idea(raw_idea(subtitles=["एक लाइन"]), ["Mystery"])
    assert idea is None
    assert "subtitle" in reason


def test_missing_hashtags_are_rejected():
    idea, reason = hackerai.normalise_idea(raw_idea(hashtags=["#one", "#two"]), ["Mystery"])
    assert idea is None
    assert "hashtag" in reason


def test_hashtags_are_normalised():
    idea, reason = hackerai.normalise_idea(
        raw_idea(hashtags=["cricket", "#India", "viral facts"]), ["Mystery"]
    )
    assert reason == ""
    assert idea is not None
    assert idea["hashtags"] == ["#cricket", "#India", "#viralfacts"]


@pytest.mark.parametrize(
    "value,expected",
    [("1:30", 90), ("10", 15), (500, 90), (45, 45), ("45 seconds", 45)],
)
def test_duration_is_parsed_and_clamped(value, expected):
    idea, _ = hackerai.normalise_idea(raw_idea(duration_sec=value), ["Mystery"])
    assert idea is not None
    assert idea["duration_sec"] == expected


def test_unknown_emotion_falls_back():
    idea, _ = hackerai.normalise_idea(raw_idea(emotion="extremely-hyped"), ["Mystery"])
    assert idea is not None
    assert idea["emotion"] == "energetic"


# ---------------------------------------------------------------------- parsing
def test_prose_reply_raises_instead_of_inventing_ideas():
    with pytest.raises(hackerai.ProviderError) as excinfo:
        hackerai.parse_ideas("Believe in yourself and great things will happen.", ["Mystery"], 10)
    assert "replied with text instead of JSON" in excinfo.value.message
    assert "Believe in yourself" in excinfo.value.message


def test_json_in_a_code_fence_is_parsed():
    payload = json.dumps({"ideas": [raw_idea()]}, ensure_ascii=False)
    result = hackerai.parse_ideas(f"```json\n{payload}\n```", ["Mystery"], 10)
    assert len(result.ideas) == 1
    assert result.rejected == 0


def test_empty_array_raises():
    with pytest.raises(hackerai.ProviderError):
        hackerai.parse_ideas('{"ideas": []}', ["Mystery"], 10)


def test_invalid_rows_are_counted_with_reasons():
    payload = json.dumps({"ideas": [raw_idea(script=LATIN_SCRIPT)]}, ensure_ascii=False)
    result = hackerai.parse_ideas(payload, ["Mystery"], 10)
    assert result.ideas == []
    assert result.rejected == 1
    assert "Devanagari" in result.reasons[0]


def test_duplicate_rows_within_a_batch_are_kept_by_the_parser():
    # De-duplication is the run service's job, not the parser's.
    payload = json.dumps({"ideas": [raw_idea(1), raw_idea(1)]}, ensure_ascii=False)
    result = hackerai.parse_ideas(payload, ["Mystery"], 10)
    assert len(result.ideas) == 2


# ------------------------------------------------------------------------ probe
class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class FakeClient:
    def __init__(self, response, captured):
        self.response = response
        self.captured = captured

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def post(self, url, headers=None, json=None):
        self.captured["url"] = url
        self.captured["headers"] = headers
        self.captured["json"] = json
        return self.response


def install_response(monkeypatch, response):
    captured: dict = {}

    def factory(*_args, **_kwargs):
        return FakeClient(response, captured)

    monkeypatch.setattr(hackerai.httpx, "Client", factory)
    return captured


def completion(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


def test_probe_accepts_a_real_answer(monkeypatch):
    captured = install_response(monkeypatch, FakeResponse(200, completion("4")))
    result = hackerai.probe("sk-test-key", "https://api.hackerai.sh/v1")
    assert result["ok"] is True
    assert captured["headers"]["Authorization"] == "Bearer sk-test-key"
    assert captured["url"].endswith("/chat/completions")
    assert captured["json"]["temperature"] == 0


def test_probe_rejects_a_canned_quote(monkeypatch):
    install_response(
        monkeypatch,
        FakeResponse(200, completion("Believe in yourself, success is a journey ✨")),
    )
    result = hackerai.probe("sk-fake", "https://api.hackerai.sh/v1")
    assert result["ok"] is False
    assert "unrelated text" in result["reason"]
    assert "sample" in result


def test_probe_reports_http_errors(monkeypatch):
    install_response(monkeypatch, FakeResponse(401, {"error": "invalid key"}, text="invalid key"))
    result = hackerai.probe("sk-bad", "https://api.hackerai.sh/v1")
    assert result["ok"] is False
    assert result["reason"].startswith("HTTP 401")


def test_probe_without_a_key_does_not_call_out(monkeypatch):
    def explode(*_args, **_kwargs):  # pragma: no cover - must not run
        raise AssertionError("probe must not call the network without a key")

    monkeypatch.setattr(hackerai.httpx, "Client", explode)
    result = hackerai.probe("", "https://api.hackerai.sh/v1")
    assert result["ok"] is False
    assert "not configured" in result["reason"]
