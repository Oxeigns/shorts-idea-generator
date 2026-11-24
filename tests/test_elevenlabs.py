from __future__ import annotations

import pytest

from app.services import elevenlabs

HINDI_TEXT = "यह एक छोटा सा हिंदी वाक्य है जो बोला जाएगा और सुना जाएगा।"


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"", text=""):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.text = text or ("" if payload is None else str(payload))

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

    def get(self, url, headers=None):
        self.captured["method"] = "GET"
        self.captured["url"] = url
        self.captured["headers"] = headers
        return self.response

    def post(self, url, headers=None, json=None):
        self.captured["method"] = "POST"
        self.captured["url"] = url
        self.captured["headers"] = headers
        self.captured["json"] = json
        return self.response


def install(monkeypatch, response):
    captured: dict = {}

    def factory(*_args, **_kwargs):
        return FakeClient(response, captured)

    monkeypatch.setattr(elevenlabs.httpx, "Client", factory)
    return captured


# ------------------------------------------------------------------ error mapping
def payment_error_response():
    return FakeResponse(
        401,
        {
            "detail": {
                "status": "payment_required",
                "message": "Your subscription has unpaid invoices.",
            }
        },
    )


def test_payment_required_maps_to_402_with_a_plain_message():
    error = elevenlabs._error(payment_error_response())
    assert error.status == 402
    assert "billing is not active" in error.message
    assert "unpaid invoices" in error.message
    assert error.code in {"payment_required", "payment"}


def test_plain_401_is_an_auth_error():
    error = elevenlabs._error(FakeResponse(401, {"detail": "Invalid API key"}))
    assert error.status == 401
    assert "rejected the API key" in error.message


def test_429_is_marked_retryable():
    error = elevenlabs._error(FakeResponse(429, {"detail": "Too many requests"}))
    assert error.status == 429
    assert error.retryable is True


# ------------------------------------------------------------------- synthesis
def test_synthesis_builds_the_documented_payload(monkeypatch):
    captured = install(monkeypatch, FakeResponse(200, content=b"ID3fake-mp3-bytes"))

    audio, meta = elevenlabs.synthesize(
        "xi-key", "voice-123", HINDI_TEXT, model_id="eleven_multilingual_v2", speed=3.0, emotion="dramatic"
    )

    assert audio == b"ID3fake-mp3-bytes"
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/text-to-speech/voice-123")
    assert captured["headers"]["xi-api-key"] == "xi-key"
    payload = captured["json"]
    assert payload["model_id"] == "eleven_multilingual_v2"
    assert payload["text"].startswith("यह एक")
    # REST range is 0.25-4.0, but the app deliberately stays inside 0.7-1.2.
    assert payload["voice_settings"]["speed"] == 1.2
    assert payload["voice_settings"]["style"] == pytest.approx(0.7)
    assert payload["voice_settings"]["use_speaker_boost"] is True
    assert meta["speed"] == 1.2
    assert meta["chars"] > 20


def test_synthesis_failure_raises_the_billing_error(monkeypatch):
    install(monkeypatch, payment_error_response())
    with pytest.raises(elevenlabs.ElevenLabsError) as excinfo:
        elevenlabs.synthesize("xi-key", "voice-123", HINDI_TEXT)
    assert excinfo.value.status == 402


def test_synthesis_rejects_empty_text_before_calling_out(monkeypatch):
    def explode(*_args, **_kwargs):  # pragma: no cover - must not run
        raise AssertionError("must not call the network for empty text")

    monkeypatch.setattr(elevenlabs.httpx, "Client", explode)
    with pytest.raises(elevenlabs.ElevenLabsError):
        elevenlabs.synthesize("xi-key", "voice-123", "  ")
    with pytest.raises(elevenlabs.ElevenLabsError):
        elevenlabs.synthesize("xi-key", "", HINDI_TEXT)


def test_empty_audio_is_an_error(monkeypatch):
    install(monkeypatch, FakeResponse(200, content=b""))
    with pytest.raises(elevenlabs.ElevenLabsError) as excinfo:
        elevenlabs.synthesize("xi-key", "voice-123", HINDI_TEXT)
    assert "empty audio" in excinfo.value.message


# ----------------------------------------------------------------------- voices
def test_voice_list_maps_labels_and_prefers_hindi(monkeypatch):
    response = FakeResponse(
        200,
        {
            "voices": [
                {
                    "voice_id": "en-1",
                    "name": "Roger",
                    "labels": {"gender": "male", "language": "en", "accent": "american"},
                    "preview_url": "https://example.test/roger.mp3",
                },
                {
                    "voice_id": "hi-1",
                    "name": "Anjali",
                    "labels": {"gender": "female", "language": "hi"},
                },
            ]
        },
    )
    install(monkeypatch, response)
    voices = elevenlabs.list_voices("xi-key")
    assert [voice["id"] for voice in voices] == ["hi-1", "en-1"]
    assert voices[1]["gender"] == "male"
    assert voices[1]["preview_url"].endswith("roger.mp3")


def test_account_surfaces_billing_status(monkeypatch):
    install(
        monkeypatch,
        FakeResponse(
            200,
            {
                "subscription": {
                    "tier": "starter",
                    "status": "past_due",
                    "character_limit": 40000,
                    "character_count": 0,
                    "can_extend_character_limit": False,
                },
                "first_name": "Yash",
            },
        ),
    )
    data = elevenlabs.account("xi-key")
    assert data["tier"] == "starter"
    assert data["status"] == "past_due"
    assert data["character_limit"] == 40000


# ------------------------------------------------------------------- cleaning
def test_clean_for_speech_strips_markdown_and_emoji():
    assert elevenlabs.clean_for_speech("**नमस्ते** 🎬 दोस्तों") == "नमस्ते दोस्तों"
    assert elevenlabs.clean_for_speech("# शीर्षक\n\nबाकी टेक्स्ट") == "शीर्षक बाकी टेक्स्ट"
