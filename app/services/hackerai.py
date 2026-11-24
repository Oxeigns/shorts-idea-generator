"""Hacker AI (OpenAI-compatible) idea generation.

Design notes
------------
* Every reply must be JSON. A prose reply is an error, never an idea: the gateway has
  been observed answering HTTP 200 with unrelated text for an unusable key, so status
  code alone proves nothing.
* Ideas are validated field by field. Anything incomplete is rejected with a reason
  instead of being padded with invented content.
* Hindi means Devanagari. A "Hindi" script written only in Latin characters is
  rejected, because it is not what the channel publishes.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

CATEGORIES: list[str] = [
    "Amazing Facts",
    "Psychology Facts",
    "Mystery",
    "Science",
    "Technology & AI",
    "Motivation",
    "Horror Stories",
    "History",
    "Space & Universe",
    "Human Behaviour",
    "Interesting Discoveries",
    "Emotional Stories",
]

CATEGORY_KEYS = {item.lower(): item for item in CATEGORIES}

EMOTIONS = ["energetic", "dramatic", "mysterious", "calm", "warm", "neutral"]

DEVANAGARI = re.compile(r"[\u0900-\u097F]")

SYSTEM_PROMPT = (
    "You are a senior YouTube Shorts strategist for an Indian Hindi channel. "
    "You write simple, everyday Hindi in Devanagari. You never invent statistics, "
    "studies, quotes, dates or names, and you never promise views. "
    "You answer with a single JSON object and nothing else."
)


class ProviderError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, sample: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.sample = sample


@dataclass
class BatchResult:
    ideas: list[dict] = field(default_factory=list)
    rejected: int = 0
    reasons: list[str] = field(default_factory=list)


def build_prompt(categories: list[str], count: int, avoid_titles: list[str], language: str = "Hindi") -> str:
    category_list = ", ".join(categories) if categories else ", ".join(CATEGORIES)
    avoid = "\n".join(f"- {title}" for title in avoid_titles[:80]) or "- (none yet)"
    return f"""Create exactly {count} original YouTube Shorts ideas for an Indian {language} channel.

Categories to draw from: {category_list}
Use a different category for each idea where possible. Every idea must have a distinct
topic AND a distinct angle — no rephrasing the same subject.

Do NOT reuse or lightly reword any of these existing titles:
{avoid}

Hard rules:
1. All Hindi content must be in Devanagari script (देवनागरी). Use simple, everyday Hindi
   that a 15-year-old understands. Avoid heavy Sanskritised words and avoid English
   sentences (a common English word like "AI" or "science" may stay).
2. Never invent a statistic, study, date, name, quote or historical event. If a detail
   is uncertain, phrase it as a question, a general observation, or say "kahani kehti hai".
   No guarantees like "100% true" or "will go viral".
3. hook = the first 2 seconds. Maximum 12 spoken words. Must create a curiosity gap.
4. script = 90-140 Hindi words of fast-paced narration with a payoff and a memorable
   closing line. Written for speaking, not reading.
5. scenes = 4 to 8 visual beats. Each beat: scene number + concrete visual suggestion.
   No copyrighted footage; describe original or generated visuals.
6. subtitles = 6 to 10 short lines in order, each at most 7 words, taken from the script.
7. voiceover_text = the exact narration for ElevenLabs: same as the script, cleaned for
   speech (no emojis, no stage directions, no markdown).
8. description = 2 SEO sentences plus a call to action, in Hindi.
9. hashtags = 5 to 10 tags, each starting with #.
10. duration_sec = an integer between 20 and 60.
11. engagement_question = one question to pin as a comment.
12. emotion = exactly one of: {", ".join(EMOTIONS)}.
13. music = a short mood description for background music.
14. category = exactly one of the categories listed above.

Return ONLY this JSON, no markdown fences, no commentary:
{{"ideas":[{{"title":"","hook":"","script":"","scenes":[{{"scene":1,"visual":""}}],"voiceover_text":"","emotion":"","music":"","subtitles":[""],"description":"","hashtags":["#"],"duration_sec":30,"engagement_question":"","category":""}}]}}"""


def chat(
    key: str,
    base_url: str,
    model: str,
    prompt: str,
    timeout: float | None = None,
) -> tuple[str, dict]:
    """Call the chat endpoint and return (assistant text, request metadata)."""
    if not key:
        raise ProviderError("Hacker AI API key is not configured. Add an sk- key in Config.")
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model or "auto",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.9,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=timeout or settings.request_timeout) as client:
            response = client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise ProviderError(f"Hacker AI is unreachable: {exc}") from exc

    if response.status_code == 400:
        # Some compatible gateways reject response_format. One retry without it.
        payload.pop("response_format", None)
        try:
            with httpx.Client(timeout=timeout or settings.request_timeout) as client:
                response = client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Hacker AI is unreachable: {exc}") from exc

    if response.status_code >= 400:
        body = response.text[:400]
        if response.status_code in {401, 403}:
            raise ProviderError(
                "Hacker AI rejected the key. An sk- inference key is required; an hsb_ "
                f"bridge token cannot generate ideas. (HTTP {response.status_code})",
                status=response.status_code,
                sample=body,
            )
        raise ProviderError(f"Hacker AI returned HTTP {response.status_code}: {body}", status=response.status_code, sample=body)

    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        raise ProviderError(
            f"Hacker AI returned an unexpected body: {response.text[:300]}", sample=response.text[:300]
        ) from exc
    return str(content or ""), {"model": data.get("model") or model, "usage": data.get("usage") or {}}


def _extract_json(text: str) -> object | None:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


def _pick(raw: dict, *names: str):
    lowered = {str(k).strip().lower().replace(" ", "_"): v for k, v in raw.items()}
    for name in names:
        key = name.lower().replace(" ", "_")
        if key in lowered and lowered[key] not in (None, "", [], {}):
            return lowered[key]
    return None


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value)
    return re.sub(r"\s+", " ", str(value)).strip()


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        parts = re.split(r"[\n•·]+", value)
        return [part.strip(" -") for part in parts if part.strip(" -")]
    return [value]


def _normalise_scenes(value) -> list[dict]:
    scenes: list[dict] = []
    for index, item in enumerate(_as_list(value), start=1):
        if isinstance(item, dict):
            number = item.get("scene") or item.get("number") or index
            visual = _text(_pick(item, "visual", "description", "suggestion", "text"))
        else:
            number, visual = index, _text(item)
        if visual:
            scenes.append({"scene": int(number) if str(number).isdigit() else index, "visual": visual})
    return scenes[:10]


def _normalise_hashtags(value) -> list[str]:
    tags: list[str] = []
    for item in _as_list(value):
        text = _text(item)
        for token in re.split(r"[,;]\s*", text):
            token = token.strip()
            if not token:
                continue
            if not token.startswith("#"):
                token = "#" + re.sub(r"[^\w\u0900-\u097F]", "", token)
            if len(token) > 1 and token not in tags:
                tags.append(token)
    return tags[:12]


def _normalise_duration(value) -> int:
    if isinstance(value, (int, float)):
        seconds = int(value)
    else:
        text = _text(value).lower()
        match = re.search(r"(\d+)\s*[:.]\s*(\d+)", text)
        if match:
            seconds = int(match.group(1)) * 60 + int(match.group(2))
        else:
            digits = re.search(r"(\d+)", text)
            seconds = int(digits.group(1)) if digits else 30
    return max(15, min(90, seconds))


def _devanagari_ratio(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for ch in letters if DEVANAGARI.match(ch)) / len(letters)


def normalise_idea(raw: dict, categories: list[str]) -> tuple[dict | None, str]:
    """Validate one raw idea. Returns (idea, "") or (None, reason)."""
    if not isinstance(raw, dict):
        return None, "idea is not an object"

    title = _text(_pick(raw, "title", "video_title", "idea_title"))
    hook = _text(_pick(raw, "hook", "viral_hook", "opening"))
    script = _text(_pick(raw, "script", "script_hindi", "hindi_script", "full_script"))
    voiceover = _text(_pick(raw, "voiceover_text", "voiceover", "narration"))
    subtitles = [_text(item) for item in _as_list(_pick(raw, "subtitles", "subtitle_text", "captions")) if _text(item)]
    scenes = _normalise_scenes(_pick(raw, "scenes", "visuals", "scene_by_scene", "visual_suggestions"))
    hashtags = _normalise_hashtags(_pick(raw, "hashtags", "tags"))
    description = _text(_pick(raw, "description", "seo_description"))
    question = _text(_pick(raw, "engagement_question", "question", "cta_question"))
    music = _text(_pick(raw, "music", "background_music", "music_suggestion"))
    emotion = _text(_pick(raw, "emotion", "voice_emotion", "tone")).lower().strip()
    duration = _normalise_duration(_pick(raw, "duration_sec", "duration", "estimated_duration"))
    category_raw = _text(_pick(raw, "category", "topic_category"))

    if not title:
        return None, "missing title"
    if not hook:
        return None, "missing hook"
    if len(script) < 80:
        return None, f"script too short ({len(script)} chars)"
    if _devanagari_ratio(script) < 0.35:
        return None, "script is not in Devanagari Hindi"
    if not voiceover:
        voiceover = script
    if len(subtitles) < 3:
        return None, "fewer than 3 subtitle lines"
    if len(scenes) < 3:
        return None, "fewer than 3 scenes"
    if len(hashtags) < 3:
        return None, "fewer than 3 hashtags"

    if emotion not in EMOTIONS:
        emotion = "energetic"
    category = CATEGORY_KEYS.get(category_raw.lower(), "")
    if not category:
        lowered = title.lower()
        category = next((item for item in (categories or CATEGORIES) if item.lower() in lowered), "")
    if not category:
        category = (categories or ["Amazing Facts"])[0]

    return (
        {
            "title": title[:240],
            "hook": hook[:400],
            "script": script,
            "scenes": scenes,
            "voiceover_text": voiceover,
            "emotion": emotion,
            "music": music or "subtle cinematic background",
            "subtitles": subtitles[:12],
            "description": description or f"{title} — {hook}",
            "hashtags": hashtags,
            "duration_sec": duration,
            "engagement_question": question or "Aapko ye baat kaise lagi? Comment karein.",
            "category": category,
        },
        "",
    )


def parse_ideas(content: str, categories: list[str], expected: int) -> BatchResult:
    payload = _extract_json(content)
    if payload is None:
        sample = re.sub(r"\s+", " ", (content or ""))[:220]
        raise ProviderError(
            "Hacker AI replied with text instead of JSON, so nothing could be saved. "
            "This usually means the key is not valid for inference. "
            f"Reply started with: {sample!r}",
            sample=sample,
        )

    rows: list
    if isinstance(payload, dict):
        candidate = _pick(payload, "ideas", "shorts", "results", "data")
        rows = candidate if isinstance(candidate, list) else []
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []

    result = BatchResult()
    for raw in rows[: max(expected * 2, expected)]:
        idea, reason = normalise_idea(raw, categories)
        if idea is None:
            result.rejected += 1
            if len(result.reasons) < 6:
                result.reasons.append(reason)
            continue
        result.ideas.append(idea)
    if not result.ideas and not result.rejected:
        raise ProviderError("Hacker AI returned an empty ideas array.")
    return result


def generate_batch(
    key: str,
    base_url: str,
    model: str,
    categories: list[str],
    count: int,
    avoid_titles: list[str],
    timeout: float | None = None,
) -> tuple[BatchResult, dict]:
    prompt = build_prompt(categories, count, avoid_titles)
    content, meta = chat(key, base_url, model, prompt, timeout=timeout)
    result = parse_ideas(content, categories, count)
    return result, meta


def probe(key: str, base_url: str, model: str = "auto", timeout: float = 30) -> dict:
    """Prove the key performs inference.

    Asking for a fact with one right answer is the only reliable check: a gateway that
    echoes a canned sentence for any credential fails it, while a real key answers 4.
    """
    if not key:
        return {"ok": False, "reason": "Hacker AI API key is not configured."}
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model or "auto",
        "messages": [{"role": "user", "content": "What is 2+2? Reply with the digit only."}],
        "temperature": 0,
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=payload
            )
    except httpx.HTTPError as exc:
        return {"ok": False, "reason": f"Hacker AI is unreachable: {exc}"}
    if response.status_code >= 400:
        return {"ok": False, "reason": f"HTTP {response.status_code}: {response.text[:200]}"}
    try:
        answer = str(response.json()["choices"][0]["message"]["content"]).strip()
    except Exception:  # noqa: BLE001
        return {"ok": False, "reason": "The reply was not an OpenAI-compatible completion."}
    if "4" not in answer or len(answer) > 24:
        return {
            "ok": False,
            "reason": "The endpoint replied with unrelated text instead of an answer, so this key is not valid for inference.",
            "sample": answer[:120],
        }
    return {"ok": True, "reason": "The model answered correctly, so the key works for inference.", "sample": answer[:40]}
