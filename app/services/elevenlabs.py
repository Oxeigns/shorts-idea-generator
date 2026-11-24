"""ElevenLabs voices and Hindi speech synthesis."""

from __future__ import annotations

import logging
import re

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE = "https://api.elevenlabs.io/v1"

EMOTION_PRESETS: dict[str, dict[str, float]] = {
    "energetic": {"stability": 0.35, "style": 0.55, "similarity_boost": 0.8},
    "dramatic": {"stability": 0.3, "style": 0.7, "similarity_boost": 0.8},
    "mysterious": {"stability": 0.45, "style": 0.45, "similarity_boost": 0.75},
    "calm": {"stability": 0.75, "style": 0.1, "similarity_boost": 0.75},
    "warm": {"stability": 0.6, "style": 0.25, "similarity_boost": 0.8},
    "neutral": {"stability": 0.5, "style": 0.0, "similarity_boost": 0.75},
}


class ElevenLabsError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, code: str = "", retryable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.retryable = retryable


def clean_for_speech(text: str) -> str:
    """Strip anything that should not be read out loud."""
    cleaned = text or ""
    cleaned = re.sub(r"```.*?```", " ", cleaned, flags=re.S)
    cleaned = re.sub(r"[*_#>~`\[\]]", " ", cleaned)
    cleaned = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _error(response: httpx.Response) -> ElevenLabsError:
    code = ""
    message = response.text[:300]
    try:
        body = response.json()
        detail = body.get("detail") if isinstance(body, dict) else None
        if isinstance(detail, dict):
            code = str(detail.get("status") or detail.get("code") or "")
            message = str(detail.get("message") or message)
        elif isinstance(detail, str):
            message = detail
    except Exception:  # noqa: BLE001
        pass
    lowered = f"{code} {message}".lower()
    if "payment" in lowered:
        return ElevenLabsError(
            f"ElevenLabs billing is not active, so voice generation is blocked: {message}",
            status=402,
            code=code or "payment_required",
        )
    if response.status_code == 401:
        return ElevenLabsError(f"ElevenLabs rejected the API key: {message}", status=401, code=code)
    if response.status_code == 429:
        return ElevenLabsError(f"ElevenLabs rate limit reached: {message}", status=429, code=code, retryable=True)
    return ElevenLabsError(f"ElevenLabs error {response.status_code}: {message}", status=response.status_code, code=code)


def list_voices(key: str, timeout: float = 30) -> list[dict]:
    if not key:
        raise ElevenLabsError("ElevenLabs API key is not configured.", status=400)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{BASE}/voices", headers={"xi-api-key": key})
    except httpx.HTTPError as exc:
        raise ElevenLabsError(f"ElevenLabs is unreachable: {exc}") from exc
    if response.status_code >= 400:
        raise _error(response)
    voices = []
    for raw in response.json().get("voices", []):
        labels = raw.get("labels") or {}
        voices.append(
            {
                "id": raw.get("voice_id"),
                "name": raw.get("name") or "",
                "gender": labels.get("gender") or "",
                "language": labels.get("language") or "",
                "accent": labels.get("accent") or "",
                "use_case": labels.get("use_case") or "",
                "preview_url": raw.get("preview_url") or "",
            }
        )
    voices.sort(key=lambda item: (item["language"] not in {"hi", "en"}, item["name"].lower()))
    return voices


def account(key: str, timeout: float = 20) -> dict:
    if not key:
        raise ElevenLabsError("ElevenLabs API key is not configured.", status=400)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{BASE}/user", headers={"xi-api-key": key})
    except httpx.HTTPError as exc:
        raise ElevenLabsError(f"ElevenLabs is unreachable: {exc}") from exc
    if response.status_code >= 400:
        raise _error(response)
    data = response.json()
    subscription = data.get("subscription") or {}
    return {
        "tier": subscription.get("tier"),
        "status": subscription.get("status"),
        "character_limit": subscription.get("character_limit"),
        "character_count": subscription.get("character_count"),
        "can_extend": subscription.get("can_extend_character_limit"),
        "first_name": data.get("first_name"),
    }


def synthesize(
    key: str,
    voice_id: str,
    text: str,
    model_id: str | None = None,
    speed: float = 1.0,
    emotion: str = "energetic",
    timeout: float | None = None,
) -> tuple[bytes, dict]:
    """Return (mp3 bytes, metadata). Raises ElevenLabsError with a readable message."""
    if not key:
        raise ElevenLabsError("ElevenLabs API key is not configured.", status=400)
    if not voice_id:
        raise ElevenLabsError("Choose an ElevenLabs voice first.", status=400)
    spoken = clean_for_speech(text)
    if len(spoken) < 20:
        raise ElevenLabsError("The voiceover text is too short to synthesize.", status=400)

    preset = EMOTION_PRESETS.get((emotion or "").lower(), EMOTION_PRESETS["energetic"])
    payload = {
        "text": spoken,
        "model_id": model_id or settings.elevenlabs_model_id,
        "voice_settings": {
            "stability": preset["stability"],
            "similarity_boost": preset["similarity_boost"],
            "style": preset["style"],
            "use_speaker_boost": True,
            "speed": max(0.7, min(1.2, float(speed or 1.0))),
        },
    }
    url = f"{BASE}/text-to-speech/{voice_id}"
    try:
        with httpx.Client(timeout=timeout or settings.request_timeout) as client:
            response = client.post(url, headers={"xi-api-key": key, "Content-Type": "application/json"}, json=payload)
    except httpx.HTTPError as exc:
        raise ElevenLabsError(f"ElevenLabs is unreachable: {exc}") from exc

    if response.status_code >= 400:
        raise _error(response)
    audio = response.content
    if not audio:
        raise ElevenLabsError("ElevenLabs returned an empty audio file.", status=502)
    return audio, {"chars": len(spoken), "model_id": payload["model_id"], "speed": payload["voice_settings"]["speed"]}
