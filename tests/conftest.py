"""Test harness.

Environment is configured before any ``app`` module is imported, because settings are
read at import time. Every test gets a clean SQLite database; no network call is made.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="shorts-ideas-tests-"))
os.environ["DATA_DIR"] = str(TMP / "data")
os.environ["DATABASE_URL"] = f"sqlite:///{TMP / 'test.db'}"
os.environ["APP_SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["ADMIN_USERNAME"] = "tester"
os.environ["ADMIN_PASSWORD"] = "test-password"
os.environ["HACKER_AI_API_KEY"] = ""
os.environ["ELEVENLABS_API_KEY"] = ""
os.environ["ALLOW_ENV_SECRETS"] = "1"
os.environ["COOKIE_SECURE"] = "0"

atexit.register(lambda: shutil.rmtree(TMP, ignore_errors=True))

import pytest  # noqa: E402


@pytest.fixture()
def db():
    """A fresh schema plus one session for the duration of the test."""
    from app import models  # noqa: F401  (register mappings)
    from app.db import Base, SessionLocal, engine

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient

    from app.main import _login_attempts, app

    _login_attempts.clear()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth_client(client):
    response = client.post(
        "/login",
        data={"username": "tester", "password": "test-password", "next": "/"},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return client
