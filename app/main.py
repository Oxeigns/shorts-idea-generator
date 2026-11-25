from __future__ import annotations

import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import netguard
from app.config import settings
from app.db import get_session, init_db
from app.models import Idea, Run, Voiceover
from app.ratelimit import SlidingWindow
from app.security import (
    read_session,
    safe_next,
    sign_session,
    verify_password,
    verify_username,
)
from app.services import elevenlabs, hackerai
from app.services import ideas as idea_service
from app.services.elevenlabs import ElevenLabsError
from app.services.hackerai import ProviderError
from app.store import (
    ELEVENLABS_API_KEY,
    HACKER_AI_API_KEY,
    all_settings,
    effective,
    get_secret,
    put_setting,
    secret_view,
    set_secret,
)
from app.timeutil import fmt_ist, ist_clock_now, ist_today, to_ist

logger = logging.getLogger(__name__)
BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
templates.env.filters["ist"] = lambda value, pattern="%d-%m-%Y %H:%M": fmt_ist(value, pattern)

COOKIE_SECURE = (os.getenv("COOKIE_SECURE") or "0").strip() in {"1", "true", "yes"}

_voice_cache: dict[str, tuple[float, list[dict]]] = {}
_login_attempts: dict[str, list[float]] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    logger.info("database ready at %s", settings.db_url)
    yield


app = FastAPI(title="AI Viral Shorts Idea Generator", version="1.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

# No template uses an inline script, inline style or inline handler, so the strict
# policy below can stay free of 'unsafe-inline'. The favicon is a data: URI.
CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "media-src 'self'; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    if settings.security_headers:
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()"
        )
        forwarded = (request.headers.get("x-forwarded-proto") or "").lower()
        if settings.hsts and (request.url.scheme == "https" or forwarded == "https"):
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
    return response


# ------------------------------------------------------------------- rate limits
# Requests that cost money or provider quota are limited per signed-in user + IP.
LIMITERS: dict[str, SlidingWindow] = {
    "generate": SlidingWindow(6, 300),
    "voice": SlidingWindow(20, 600),
    "regenerate": SlidingWindow(20, 600),
    "probe": SlidingWindow(12, 60),
}


def reset_rate_limits() -> None:
    for limiter in LIMITERS.values():
        limiter.reset()


def _limit(name: str, request: Request) -> None:
    user = _user(request) or "anonymous"
    ip = request.client.host if request.client else "unknown"
    wait = LIMITERS[name].hit(f"{name}:{user}:{ip}")
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Try again in {wait} seconds.",
            headers={"Retry-After": str(wait)},
        )


# --------------------------------------------------------------------------- auth
def _user(request: Request) -> str | None:
    return read_session(request.cookies.get(settings.cookie_name))


def require_api(request: Request) -> str:
    user = _user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to use this endpoint.")
    return user


THEMES = {"dark", "light", "system"}


def _theme(request: Request) -> str:
    value = (request.cookies.get("theme") or "").strip().lower()
    return value if value in THEMES else "dark"


def _page(request: Request, name: str, **ctx) -> HTMLResponse | RedirectResponse:
    user = _user(request)
    if not user:
        target = request.url.path
        if request.url.query:
            target = f"{target}?{request.url.query}"
        return RedirectResponse(f"/login?next={target}", status_code=303)
    payload = {
        "request": request,
        "user": user,
        "path": request.url.path,
        "clock": ist_clock_now(),
        "categories": hackerai.CATEGORIES,
        "emotions": hackerai.EMOTIONS,
        "cfg": settings,
        "theme": _theme(request),
    }
    payload.update(ctx)
    return templates.TemplateResponse(request, name, payload)


def _too_many_attempts(ip: str) -> bool:
    now = time.time()
    window = [stamp for stamp in _login_attempts.get(ip, []) if now - stamp < 300]
    _login_attempts[ip] = window
    return len(window) >= 10


def _record_attempt(ip: str) -> None:
    _login_attempts.setdefault(ip, []).append(time.time())


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    if _user(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "request": request,
            "next": safe_next(next),
            "error": "",
            "clock": ist_clock_now(),
            "theme": _theme(request),
        },
    )


@app.post("/login")
def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
):
    ip = request.client.host if request.client else "unknown"
    if _too_many_attempts(ip):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "request": request,
                "next": safe_next(next),
                "error": "Too many attempts. Wait five minutes.",
                "clock": ist_clock_now(),
                "theme": _theme(request),
            },
            status_code=429,
        )
    if not (verify_username(username) and verify_password(password)):
        _record_attempt(ip)
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "request": request,
                "next": safe_next(next),
                "error": "Wrong username or password.",
                "clock": ist_clock_now(),
                "theme": _theme(request),
            },
            status_code=401,
        )
    response = RedirectResponse(safe_next(next) or "/", status_code=303)
    response.set_cookie(
        settings.cookie_name,
        sign_session(settings.admin_username),
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        max_age=settings.session_days * 86400,
    )
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(settings.cookie_name)
    return response


# -------------------------------------------------------------------------- pages
@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_session),
    q: str = "",
    saved: int = 0,
    run: int = 0,
):
    idea_service.reap_stale(db)
    rows = idea_service.list_ideas(db, query=q, saved_only=bool(saved), run_id=run or None)
    count = idea_service.stats(db)
    last_run = db.scalar(select(Run).order_by(Run.id.desc()))
    running = idea_service.active_run(db)
    today = ist_today()
    for idea in rows:
        local = to_ist(idea.created_at)
        idea_is_today = bool(local and local.date() == today)  # type: ignore[attr-defined]
        idea.is_today = idea_is_today  # type: ignore[attr-defined]  # view-only flag
    eleven = secret_view(db, ELEVENLABS_API_KEY)
    hacker = secret_view(db, HACKER_AI_API_KEY)
    return _page(
        request,
        "dashboard.html",
        ideas=rows,
        count=count,
        last_run=last_run,
        running=running,
        q=q,
        saved_filter=bool(saved),
        run_filter=run,
        eleven=eleven,
        hacker=hacker,
        default_voice=effective(db, "elevenlabs_voice_id", settings.elevenlabs_voice_id),
        default_speed=effective(db, "default_speed", "1.0"),
        default_emotion=effective(db, "default_emotion", "energetic"),
        voices_enabled=eleven["configured"],
        truncated=len(rows) >= 200,
    )


@app.get("/history", response_class=HTMLResponse)
def history(request: Request, db: Session = Depends(get_session)):
    runs = list(db.scalars(select(Run).order_by(Run.id.desc()).limit(60)).all())
    counts = dict(
        db.execute(
            select(Idea.run_id, func.count(Idea.id)).where(Idea.run_id.isnot(None)).group_by(Idea.run_id)
        ).all()
    )
    return _page(request, "history.html", runs=runs, counts=counts)


@app.get("/config", response_class=HTMLResponse)
def config_page(request: Request, db: Session = Depends(get_session), saved: int = 0, error: str = ""):
    hacker = secret_view(db, HACKER_AI_API_KEY)
    eleven = secret_view(db, ELEVENLABS_API_KEY)
    values = {
        "hacker_ai_model": effective(db, "hacker_ai_model", settings.hackerai_model),
        "hacker_ai_base_url": effective(db, "hacker_ai_base_url", settings.hackerai_base_url),
        "elevenlabs_voice_id": effective(db, "elevenlabs_voice_id", settings.elevenlabs_voice_id),
        "elevenlabs_model_id": effective(db, "elevenlabs_model_id", settings.elevenlabs_model_id),
        "default_speed": effective(db, "default_speed", "1.0"),
        "default_emotion": effective(db, "default_emotion", "energetic"),
    }
    voices: list[dict] = []
    voice_error = ""
    account = None
    account_error = ""
    key = get_secret(db, ELEVENLABS_API_KEY)
    if key:
        try:
            voices = _voices(db, key, force=True)
        except ElevenLabsError as exc:
            voice_error = exc.message
        try:
            account = elevenlabs.account(key)
        except ElevenLabsError as exc:
            account_error = exc.message
    return _page(
        request,
        "config.html",
        hacker=hacker,
        eleven=eleven,
        values=values,
        voices=voices,
        voice_error=voice_error,
        account=account,
        account_error=account_error,
        saved=bool(saved),
        error=error,
        env_files=all_settings(db),
    )


@app.post("/config")
def config_save(
    request: Request,
    db: Session = Depends(get_session),
    hacker_ai_api_key: str = Form(""),
    elevenlabs_api_key: str = Form(""),
    hacker_ai_model: str = Form("auto"),
    hacker_ai_base_url: str = Form(""),
    elevenlabs_voice_id: str = Form(""),
    elevenlabs_model_id: str = Form(""),
    default_speed: str = Form("1.0"),
    default_emotion: str = Form("energetic"),
    clear_hacker_ai: str = Form(""),
    clear_elevenlabs: str = Form(""),
):
    require_api(request)

    # Validate everything before writing, so a rejected value never leaves the
    # configuration half updated.
    model = (hacker_ai_model or "").strip() or "auto"
    if not re.fullmatch(r"[A-Za-z0-9._:/-]{1,64}", model):
        return RedirectResponse(
            "/config?error=" + quote("Model name contains unsupported characters."), status_code=303
        )
    try:
        base_url = netguard.validate_base_url(hacker_ai_base_url.strip() or settings.hackerai_base_url)
    except netguard.InvalidBaseURL as exc:
        return RedirectResponse("/config?error=" + quote(str(exc)), status_code=303)

    voice = (elevenlabs_voice_id or "").strip() or settings.elevenlabs_voice_id
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", voice):
        return RedirectResponse(
            "/config?error=" + quote("Voice ID may only contain letters, digits, dashes and underscores."),
            status_code=303,
        )
    voice_model = (elevenlabs_model_id or "").strip() or settings.elevenlabs_model_id
    if not re.fullmatch(r"[A-Za-z0-9._-]{2,64}", voice_model):
        return RedirectResponse(
            "/config?error=" + quote("ElevenLabs model ID is not valid."), status_code=303
        )

    try:
        speed = max(0.7, min(1.2, float(default_speed)))
    except ValueError:
        speed = 1.0
    emotion = default_emotion if default_emotion in hackerai.EMOTIONS else "energetic"

    if clear_hacker_ai:
        set_secret(db, HACKER_AI_API_KEY, "")
    if hacker_ai_api_key.strip():
        set_secret(db, HACKER_AI_API_KEY, hacker_ai_api_key)
    if clear_elevenlabs:
        set_secret(db, ELEVENLABS_API_KEY, "")
    if elevenlabs_api_key.strip():
        set_secret(db, ELEVENLABS_API_KEY, elevenlabs_api_key)

    put_setting(db, "hacker_ai_model", model)
    put_setting(db, "hacker_ai_base_url", base_url)
    put_setting(db, "elevenlabs_voice_id", voice)
    put_setting(db, "elevenlabs_model_id", voice_model)
    put_setting(db, "default_speed", f"{speed:.2f}")
    put_setting(db, "default_emotion", emotion)
    _voice_cache.clear()
    return RedirectResponse("/config?saved=1", status_code=303)


# ---------------------------------------------------------------------------- api
class GenerateRequest(BaseModel):
    count: int = 10
    categories: list[str] = Field(default_factory=list)
    auto: bool = False


class VoiceRequest(BaseModel):
    voice_id: str | None = None
    speed: float | None = None
    emotion: str | None = None


@app.get("/api/health")
def health(db: Session = Depends(get_session)):
    return {
        "ok": True,
        "version": app.version,
        "ideas": db.scalar(select(func.count(Idea.id)).where(Idea.status == "active")) or 0,
        "runs": db.scalar(select(func.count(Run.id))) or 0,
        "database": "sqlite" if settings.db_url.startswith("sqlite") else "external",
    }


@app.post("/api/ideas/generate")
def generate(payload: GenerateRequest, request: Request, db: Session = Depends(get_session)):
    require_api(request)
    if payload.count not in idea_service.ALLOWED_COUNTS:
        raise HTTPException(400, "Choose 10, 20 or 50 ideas.")
    _limit("generate", request)
    if not get_secret(db, HACKER_AI_API_KEY):
        raise HTTPException(
            400,
            "No Hacker AI key saved. Open Config and add your sk- inference key first.",
        )
    try:
        run = idea_service.start_run(db, payload.count, payload.categories, payload.auto)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return idea_service.run_view(db, run)


@app.get("/api/runs/{run_id}")
def run_status(run_id: int, request: Request, db: Session = Depends(get_session)):
    require_api(request)
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "Run not found.")
    return idea_service.run_view(db, run)


@app.get("/api/ideas")
def ideas_json(request: Request, db: Session = Depends(get_session), q: str = "", saved: int = 0, run: int = 0):
    require_api(request)
    rows = idea_service.list_ideas(db, query=q, saved_only=bool(saved), run_id=run or None)
    return {"ideas": [idea.as_dict() for idea in rows], "count": len(rows)}


@app.post("/api/ideas/{idea_id}/save")
def toggle_save(idea_id: int, request: Request, db: Session = Depends(get_session)):
    require_api(request)
    idea = db.get(Idea, idea_id)
    if idea is None or idea.status != "active":
        raise HTTPException(404, "Idea not found.")
    idea.saved = not idea.saved
    db.commit()
    return {"id": idea.id, "saved": idea.saved}


@app.delete("/api/ideas/{idea_id}")
def delete_idea(idea_id: int, request: Request, db: Session = Depends(get_session)):
    require_api(request)
    try:
        files = idea_service.delete_idea(db, idea_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"ok": True, "deleted": idea_id, "files_removed": files}


@app.post("/api/ideas/{idea_id}/regenerate")
def regenerate(idea_id: int, request: Request, db: Session = Depends(get_session)):
    require_api(request)
    _limit("regenerate", request)
    if not get_secret(db, HACKER_AI_API_KEY):
        raise HTTPException(400, "No Hacker AI key saved. Open Config first.")
    try:
        new_idea = idea_service.regenerate(db, idea_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(502, exc.message) from exc
    return {"ok": True, "replaced": idea_id, "idea": new_idea.as_dict()}


def _voices(db: Session, key: str, force: bool = False) -> list[dict]:
    cache_key = key[-8:]
    cached = _voice_cache.get(cache_key)
    if cached and not force and time.time() - cached[0] < 300:
        return cached[1]
    voices = elevenlabs.list_voices(key)
    _voice_cache[cache_key] = (time.time(), voices)
    return voices


@app.get("/api/voices")
def voices_api(request: Request, db: Session = Depends(get_session), refresh: int = 0):
    require_api(request)
    key = get_secret(db, ELEVENLABS_API_KEY)
    if not key:
        return {"configured": False, "voices": [], "default": ""}
    try:
        voices = _voices(db, key, force=bool(refresh))
    except ElevenLabsError as exc:
        raise HTTPException(exc.status or 502, exc.message) from exc
    return {
        "configured": True,
        "voices": voices,
        "default": effective(db, "elevenlabs_voice_id", settings.elevenlabs_voice_id),
    }


@app.post("/api/ideas/{idea_id}/voice")
def make_voice(idea_id: int, payload: VoiceRequest, request: Request, db: Session = Depends(get_session)):
    require_api(request)
    _limit("voice", request)
    idea = db.get(Idea, idea_id)
    if idea is None:
        raise HTTPException(404, "Idea not found.")
    key = get_secret(db, ELEVENLABS_API_KEY)
    if not key:
        raise HTTPException(400, "No ElevenLabs key saved. Open Config first.")

    voice_id = (payload.voice_id or "").strip() or effective(db, "elevenlabs_voice_id", settings.elevenlabs_voice_id)
    speed = payload.speed if payload.speed is not None else float(effective(db, "default_speed", "1.0"))
    emotion = payload.emotion or effective(db, "default_emotion", "energetic")
    model_id = effective(db, "elevenlabs_model_id", settings.elevenlabs_model_id)

    voice_name = ""
    try:
        for item in _voices(db, key):
            if item["id"] == voice_id:
                voice_name = item["name"]
                break
    except ElevenLabsError:
        pass

    try:
        audio, meta = elevenlabs.synthesize(
            key, voice_id, idea.voiceover_text, model_id=model_id, speed=speed, emotion=emotion
        )
    except ElevenLabsError as exc:
        db.add(
            Voiceover(
                idea_id=idea.id,
                voice_id=voice_id,
                voice_name=voice_name,
                model_id=model_id,
                emotion=emotion,
                speed=float(speed),
                chars=len(idea.voiceover_text or ""),
                status="failed",
                error=exc.message[:500],
            )
        )
        db.commit()
        raise HTTPException(status_code=exc.status or 502, detail=exc.message) from exc

    filename = f"idea-{idea.id}-{uuid.uuid4().hex[:10]}.mp3"
    path = settings.voice_dir / filename
    path.write_bytes(audio)

    record = Voiceover(
        idea_id=idea.id,
        voice_id=voice_id,
        voice_name=voice_name,
        model_id=meta["model_id"],
        emotion=emotion,
        speed=float(meta["speed"]),
        chars=int(meta["chars"]),
        bytes=len(audio),
        path=str(path),
        status="ready",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {
        "ok": True,
        "voiceover_id": record.id,
        "url": f"/voice/{record.id}.mp3",
        "download": f"/voice/{record.id}/download",
        "bytes": record.bytes,
        "chars": record.chars,
        "voice_id": voice_id,
        "voice_name": voice_name,
        "speed": record.speed,
        "model_id": record.model_id,
    }


@app.get("/voice/{voice_id}.mp3")
def voice_file(voice_id: int, request: Request, db: Session = Depends(get_session)):
    require_api(request)
    record = db.get(Voiceover, voice_id)
    if record is None or record.status != "ready":
        raise HTTPException(404, "Voiceover not found.")
    path = Path(record.path)
    if not path.exists():
        raise HTTPException(404, "The audio file is missing on disk.")
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/voice/{voice_id}/download")
def voice_download(voice_id: int, request: Request, db: Session = Depends(get_session)):
    require_api(request)
    record = db.get(Voiceover, voice_id)
    if record is None or record.status != "ready":
        raise HTTPException(404, "Voiceover not found.")
    path = Path(record.path)
    if not path.exists():
        raise HTTPException(404, "The audio file is missing on disk.")
    return FileResponse(path, media_type="audio/mpeg", filename=f"short-idea-{record.idea_id}-voice.mp3")


@app.post("/api/test/hackerai")
def test_hackerai(request: Request, db: Session = Depends(get_session)):
    require_api(request)
    _limit("probe", request)
    key = get_secret(db, HACKER_AI_API_KEY)
    base = effective(db, "hacker_ai_base_url", settings.hackerai_base_url)
    model = effective(db, "hacker_ai_model", settings.hackerai_model)
    return hackerai.probe(key, base, model)


@app.post("/api/test/elevenlabs")
def test_elevenlabs(request: Request, db: Session = Depends(get_session)):
    require_api(request)
    _limit("probe", request)
    key = get_secret(db, ELEVENLABS_API_KEY)
    if not key:
        return {"ok": False, "reason": "No ElevenLabs key saved."}
    try:
        account = elevenlabs.account(key)
        voices = elevenlabs.list_voices(key)
    except ElevenLabsError as exc:
        return {"ok": False, "reason": exc.message}
    status = str(account.get("status") or "")
    return {
        "ok": True,
        "tts_ready": status.lower() in {"active", "trialing"},
        "account": account,
        "voices": len(voices),
        "reason": (
            "Key works and billing is active."
            if status.lower() in {"active", "trialing"}
            else f"Key works, but the subscription status is '{status}', so speech generation will be refused until billing is fixed."
        ),
    }


@app.get("/api/meta")
def meta(request: Request, db: Session = Depends(get_session)):
    require_api(request)
    return {
        "categories": hackerai.CATEGORIES,
        "emotions": hackerai.EMOTIONS,
        "defaults": {
            "voice_id": effective(db, "elevenlabs_voice_id", settings.elevenlabs_voice_id),
            "speed": effective(db, "default_speed", "1.0"),
            "emotion": effective(db, "default_emotion", "energetic"),
        },
    }


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):  # noqa: ANN001
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None)
        )
    if exc.status_code == 401:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "request": request,
            "code": exc.status_code,
            "message": str(exc.detail),
            "clock": ist_clock_now(),
            "theme": _theme(request),
        },
        status_code=exc.status_code,
    )


@app.exception_handler(404)
def not_found(request: Request, exc: HTTPException):  # noqa: ANN001
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    return RedirectResponse("/", status_code=303)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):  # noqa: ANN001
    logger.exception("Unhandled error on %s", request.url.path)
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {"detail": "The server hit an unexpected error. It has been logged; check the console."},
            status_code=500,
        )
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "request": request,
            "code": 500,
            "message": "The server hit an unexpected error. It has been logged; check the console.",
            "clock": ist_clock_now(),
            "theme": _theme(request),
        },
        status_code=500,
    )
