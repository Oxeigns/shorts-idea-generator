"""Idea generation orchestration.

Generation runs in a worker thread and commits after every batch, so a 50-idea request
never blocks a page load and the dashboard can show real progress. Duplicate ideas are
dropped locally as well as being discouraged in the prompt.
"""

from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Idea, Run, Voiceover
from app.services import hackerai
from app.services.hackerai import ProviderError
from app.store import HACKER_AI_API_KEY, effective, get_secret
from app.timeutil import as_utc, utcnow

logger = logging.getLogger(__name__)

BATCH_SIZE = 10
ALLOWED_COUNTS = (10, 20, 50)
STALE_AFTER = timedelta(minutes=20)

executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ideas")


# ------------------------------------------------------------------- duplicates
def _norm_title(text: str) -> str:
    return re.sub(r"[^\w\u0900-\u097F]+", " ", (text or "").lower()).strip()


def _tokens(text: str) -> set[str]:
    return {word for word in _norm_title(text).split() if len(word) > 2}


def similarity(left: str, right: str) -> float:
    """0..1 title similarity used to reject near-duplicate ideas."""
    a, b = _norm_title(left), _norm_title(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    tokens_a, tokens_b = _tokens(left), _tokens(right)
    if tokens_a and tokens_b:
        jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
        if jaccard >= 0.8:
            return 1.0
        if len(a) >= 18 and (a in b or b in a):
            return 0.95
        return jaccard
    return 0.0


def is_duplicate(title: str, existing: list[str], threshold: float = 0.8) -> bool:
    return any(similarity(title, other) >= threshold for other in existing)


# ------------------------------------------------------------------------ helpers
def recent_titles(db: Session, limit: int = 200) -> list[str]:
    rows = db.scalars(
        select(Idea.title).where(Idea.status == "active").order_by(Idea.id.desc()).limit(limit)
    ).all()
    return [str(row) for row in rows]


def reap_stale(db: Session) -> int:
    """A crashed worker must not block new runs forever."""
    cutoff = utcnow() - STALE_AFTER
    rows = db.scalars(select(Run).where(Run.status.in_(("queued", "running")))).all()
    reaped = 0
    for run in rows:
        started = as_utc(run.started_at or run.created_at)
        if started and started < cutoff:
            run.status = "failed"
            run.error = "The worker stopped before finishing (server restart?). Start a new run."
            run.finished_at = utcnow()
            reaped += 1
    if reaped:
        db.commit()
    return reaped


def active_run(db: Session) -> Run | None:
    return db.scalar(select(Run).where(Run.status.in_(("queued", "running"))).order_by(Run.id.desc()))


def start_run(db: Session, count: int, categories: list[str], auto: bool) -> Run:
    if count not in ALLOWED_COUNTS:
        raise ValueError("Choose 10, 20 or 50 ideas.")
    reap_stale(db)
    running = active_run(db)
    if running is not None:
        raise RuntimeError(f"Run #{running.id} is still generating. Wait for it to finish.")

    chosen = list(hackerai.CATEGORIES) if auto or not categories else [c for c in categories if c in hackerai.CATEGORIES]
    if not chosen:
        chosen = list(hackerai.CATEGORIES)

    run = Run(
        categories_json=json.dumps(chosen, ensure_ascii=False),
        auto=bool(auto or not categories),
        requested=count,
        status="queued",
        provider="hackerai",
        model=effective(db, "hacker_ai_model", settings.hackerai_model),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    executor.submit(execute_run, run.id)
    return run


def _save_idea(db: Session, run: Run | None, data: dict, model: str) -> Idea:
    idea = Idea(
        run_id=run.id if run else None,
        title=data["title"],
        hook=data["hook"],
        script_hi=data["script"],
        scenes_json=json.dumps(data["scenes"], ensure_ascii=False),
        voiceover_text=data["voiceover_text"],
        emotion=data["emotion"],
        music=data["music"],
        subtitles_json=json.dumps(data["subtitles"], ensure_ascii=False),
        description=data["description"],
        hashtags_json=json.dumps(data["hashtags"], ensure_ascii=False),
        duration_sec=data["duration_sec"],
        engagement_question=data["engagement_question"],
        category=data["category"],
        provider="hackerai",
        model=model,
        status="active",
    )
    db.add(idea)
    return idea


def execute_run(run_id: int) -> None:
    """Worker entry point. Own session: the request session is already closed."""
    started = time.monotonic()
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        if run is None:
            return
        run.status = "running"
        run.started_at = utcnow()
        db.commit()

        key = get_secret(db, HACKER_AI_API_KEY)
        base_url = effective(db, "hacker_ai_base_url", settings.hackerai_base_url)
        model = effective(db, "hacker_ai_model", settings.hackerai_model)
        categories = run.categories or list(hackerai.CATEGORIES)
        avoid = recent_titles(db)

        remaining = run.requested
        empty_batches = 0
        while remaining > 0:
            batch_count = min(BATCH_SIZE, remaining)
            try:
                result, meta = hackerai.generate_batch(
                    key, base_url, model, categories, batch_count, avoid
                )
            except ProviderError as exc:
                logger.warning("run %s failed: %s", run_id, exc.message)
                run.status = "failed"
                run.error = exc.message
                run.finished_at = utcnow()
                run.duration_ms = int((time.monotonic() - started) * 1000)
                db.commit()
                return
            except Exception as exc:  # noqa: BLE001
                logger.exception("run %s crashed", run_id)
                run.status = "failed"
                run.error = f"Unexpected error: {exc}"
                run.finished_at = utcnow()
                run.duration_ms = int((time.monotonic() - started) * 1000)
                db.commit()
                return

            model_used = str(meta.get("model") or model)
            accepted = 0
            for data in result.ideas:
                if accepted >= remaining:
                    break
                if is_duplicate(data["title"], avoid):
                    run.rejected += 1
                    continue
                _save_idea(db, run, data, model_used)
                avoid.append(data["title"])
                accepted += 1

            run.generated += accepted
            run.rejected += result.rejected
            run.model = model_used
            remaining -= batch_count
            db.commit()

            if result.ideas:
                empty_batches = 0
            else:
                empty_batches += 1
            if empty_batches >= 2:
                run.status = "failed"
                reasons = "; ".join(result.reasons) or "no usable ideas in two batches"
                run.error = f"The model returned invalid ideas: {reasons}"
                run.finished_at = utcnow()
                run.duration_ms = int((time.monotonic() - started) * 1000)
                db.commit()
                return

        run.status = "done"
        run.finished_at = utcnow()
        run.duration_ms = int((time.monotonic() - started) * 1000)
        if run.generated == 0:
            run.status = "failed"
            run.error = "No idea passed validation. Check the API key and try again."
        db.commit()


def run_view(db: Session, run: Run) -> dict:
    return {
        "id": run.id,
        "status": run.status,
        "requested": run.requested,
        "generated": run.generated,
        "rejected": run.rejected,
        "error": run.error,
        "auto": run.auto,
        "categories": run.categories,
        "model": run.model,
        "duration_ms": run.duration_ms,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


# --------------------------------------------------------------------- regenerate
def regenerate(db: Session, idea_id: int) -> Idea:
    """Replace one idea with a fresh one in the same category."""
    idea = db.get(Idea, idea_id)
    if idea is None:
        raise ValueError("Idea not found.")

    key = get_secret(db, HACKER_AI_API_KEY)
    base_url = effective(db, "hacker_ai_base_url", settings.hackerai_base_url)
    model = effective(db, "hacker_ai_model", settings.hackerai_model)
    avoid = [title for title in recent_titles(db) if similarity(title, idea.title) < 0.8]

    result, meta = hackerai.generate_batch(key, base_url, model, [idea.category], 1, avoid, timeout=60)
    fresh = next((item for item in result.ideas if not is_duplicate(item["title"], avoid)), None)
    if fresh is None:
        raise ProviderError("The model only returned duplicates. Try again.")

    new_idea = _save_idea(db, None, fresh, str(meta.get("model") or model))
    db.flush()
    idea.status = "replaced"
    idea.replaced_by = new_idea.id
    db.commit()
    db.refresh(new_idea)
    return new_idea


# ------------------------------------------------------------------------- delete
def delete_idea(db: Session, idea_id: int) -> int:
    """Soft-delete an idea and erase its audio files.

    The row is kept as a tombstone so run counters stay accurate, but it is
    excluded from every listing and its MP3s are removed from disk. Returns the
    number of audio files removed.
    """
    idea = db.get(Idea, idea_id)
    if idea is None or idea.status == "deleted":
        raise ValueError("Idea not found.")

    removed = 0
    for item in list(idea.voiceovers):
        if item.path:
            path = Path(item.path)
            try:
                if path.is_file():
                    path.unlink()
                    removed += 1
            except OSError:
                logger.warning("Could not remove voiceover file %s", path)
        db.delete(item)
    idea.status = "deleted"
    idea.replaced_by = None
    db.commit()
    return removed


# ------------------------------------------------------------------------- search
def list_ideas(
    db: Session,
    query: str = "",
    saved_only: bool = False,
    run_id: int | None = None,
    limit: int = 200,
) -> list[Idea]:
    stmt = select(Idea).where(Idea.status == "active")
    if saved_only:
        stmt = stmt.where(Idea.saved.is_(True))
    if run_id:
        stmt = stmt.where(Idea.run_id == run_id)

    # Filter in SQL, then limit. Filtering a limited page in Python meant search only
    # ever looked at the newest N rows and silently missed older ideas.
    needle = (query or "").strip()
    if needle:
        pattern = f"%{needle.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Idea.title).like(pattern),
                func.lower(Idea.hook).like(pattern),
                func.lower(Idea.script_hi).like(pattern),
                func.lower(Idea.category).like(pattern),
                func.lower(Idea.hashtags_json).like(pattern),
                func.lower(Idea.description).like(pattern),
            )
        )

    stmt = stmt.order_by(Idea.created_at.desc(), Idea.id.desc()).limit(max(1, min(limit, 500)))
    return list(db.scalars(stmt).all())


def stats(db: Session) -> dict:
    from app.timeutil import ist_day_bounds_utc

    start, end = ist_day_bounds_utc()
    active = Idea.status == "active"
    return {
        "total": db.scalar(select(func.count(Idea.id)).where(active)) or 0,
        "saved": db.scalar(select(func.count(Idea.id)).where(active, Idea.saved.is_(True))) or 0,
        "today": db.scalar(
            select(func.count(Idea.id)).where(active, Idea.created_at >= start, Idea.created_at < end)
        )
        or 0,
        "runs": db.scalar(select(func.count(Run.id))) or 0,
        "voiceovers": db.scalar(
            select(func.count(Voiceover.id)).where(Voiceover.status == "ready")
        )
        or 0,
    }
