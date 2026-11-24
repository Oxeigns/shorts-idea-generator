from __future__ import annotations

import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Idea, Run
from app.services import hackerai
from app.services import ideas as service
from app.services.hackerai import BatchResult, ProviderError
from app.timeutil import utcnow
from tests.helpers import valid_idea


# ----------------------------------------------------------------- similarity
def test_identical_titles_are_duplicates():
    assert service.similarity("Samudra ka rahasya", "samudra ka rahasya!") == 1.0
    assert service.similarity("समुद्र का रहस्य", "समुद्र का रहस्य") == 1.0


def test_near_identical_titles_are_duplicates():
    left = "The deepest place on Earth mystery"
    right = "The deepest place on Earth mystery revealed"
    assert service.similarity(left, right) >= 0.8
    assert service.is_duplicate(right, [left])


def test_unrelated_titles_are_not_duplicates():
    assert service.similarity("Deep ocean trench", "Space telescope discovery") < 0.8
    assert not service.is_duplicate("Space telescope discovery", ["Deep ocean trench"])


# ----------------------------------------------------------------- stale runs
def test_stale_runs_are_reaped(db):
    old = utcnow() - timedelta(minutes=30)
    run = Run(requested=10, status="running", created_at=old, started_at=old)
    db.add(run)
    db.commit()

    assert service.reap_stale(db) == 1
    db.refresh(run)
    assert run.status == "failed"
    assert "worker stopped" in run.error


def test_fresh_runs_are_not_reaped(db):
    run = Run(requested=10, status="running", created_at=utcnow(), started_at=utcnow())
    db.add(run)
    db.commit()
    assert service.reap_stale(db) == 0
    db.refresh(run)
    assert run.status == "running"


# ------------------------------------------------------------------- start_run
@pytest.fixture()
def no_worker(monkeypatch):
    """Keep start_run from actually launching a background thread."""
    calls = []

    def submit(fn, *args, **kwargs):  # noqa: ANN001
        calls.append((fn, args, kwargs))
        return None

    monkeypatch.setattr(service.executor, "submit", submit)
    return calls


def test_start_run_expands_auto_to_all_categories(db, no_worker):
    run = service.start_run(db, 20, [], auto=True)
    assert run.status == "queued"
    assert run.requested == 20
    assert run.auto is True
    assert run.categories == hackerai.CATEGORIES
    assert len(no_worker) == 1


def test_start_run_refuses_a_second_concurrent_run(db, no_worker):
    first = service.start_run(db, 10, ["Science"], auto=False)
    with pytest.raises(RuntimeError) as excinfo:
        service.start_run(db, 10, ["Science"], auto=False)
    assert f"Run #{first.id}" in str(excinfo.value)


def test_start_run_rejects_unsupported_counts(db, no_worker):
    with pytest.raises(ValueError):
        service.start_run(db, 7, [], auto=True)


# ----------------------------------------------------------------- execute_run
def make_run(db, requested=10) -> Run:
    run = Run(
        categories_json=json.dumps(hackerai.CATEGORIES),
        auto=True,
        requested=requested,
        status="queued",
        model="auto",
        created_at=utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def test_execute_run_saves_validated_ideas(db, monkeypatch):
    run = make_run(db, 10)
    batch = BatchResult(ideas=[valid_idea(i) for i in range(1, 11)], rejected=0)

    monkeypatch.setattr(
        hackerai, "generate_batch", lambda *a, **k: (batch, {"model": "kimi-k2.5"})
    )

    service.execute_run(run.id)

    with SessionLocal() as check:
        stored = check.get(Run, run.id)
        assert stored is not None
        assert stored.status == "done"
        assert stored.generated == 10
        assert stored.rejected == 0
        assert stored.model == "kimi-k2.5"
        assert check.scalar(select(func.count(Idea.id))) == 10
        titles = check.scalars(select(Idea.title)).all()
        assert len(set(titles)) == 10


def test_execute_run_drops_cross_batch_duplicates(db, monkeypatch):
    run = make_run(db, 20)
    same = [valid_idea(i) for i in range(1, 11)]
    batch = BatchResult(ideas=same, rejected=0)

    monkeypatch.setattr(hackerai, "generate_batch", lambda *a, **k: (batch, {"model": "auto"}))

    service.execute_run(run.id)

    with SessionLocal() as check:
        stored = check.get(Run, run.id)
        assert stored is not None
        assert stored.status == "done"
        assert stored.generated == 10, "the second identical batch must be dropped"
        assert stored.rejected == 10
        assert check.scalar(select(func.count(Idea.id))) == 10


def test_execute_run_reports_provider_errors(db, monkeypatch):
    run = make_run(db, 10)

    def fail(*_args, **_kwargs):
        raise ProviderError("Hacker AI rejected the key.", status=401)

    monkeypatch.setattr(hackerai, "generate_batch", fail)

    service.execute_run(run.id)

    with SessionLocal() as check:
        stored = check.get(Run, run.id)
        assert stored is not None
        assert stored.status == "failed"
        assert "rejected the key" in stored.error
        assert check.scalar(select(func.count(Idea.id))) == 0


def test_execute_run_fails_when_nothing_validates(db, monkeypatch):
    # Two consecutive empty batches are what surface the model's reasons.
    run = make_run(db, 20)
    batch = BatchResult(ideas=[], rejected=10, reasons=["missing title"])

    monkeypatch.setattr(hackerai, "generate_batch", lambda *a, **k: (batch, {"model": "auto"}))

    service.execute_run(run.id)

    with SessionLocal() as check:
        stored = check.get(Run, run.id)
        assert stored is not None
        assert stored.status == "failed"
        assert "missing title" in stored.error


# --------------------------------------------------------------------- queries
def test_list_and_stats(db):
    run = make_run(db, 2)
    data = valid_idea()
    first = service._save_idea(db, run, data, "auto")
    db.commit()
    second = service._save_idea(db, run, valid_idea(2), "auto")
    db.commit()
    first.saved = True
    db.commit()

    all_rows = service.list_ideas(db)
    assert {row.id for row in all_rows} == {first.id, second.id}
    assert [row.id for row in service.list_ideas(db, query="समुद्र")]

    stats = service.stats(db)
    assert stats["total"] == 2
    assert stats["saved"] == 1
    assert stats["runs"] == 1


def test_run_view_is_json_safe(db):
    run = make_run(db, 10)
    view = service.run_view(db, run)
    assert view["id"] == run.id
    assert isinstance(view["created_at"], str)
    json.dumps(view)  # must not raise
