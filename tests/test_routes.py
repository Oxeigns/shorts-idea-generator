from __future__ import annotations

from app import store


def test_health_is_public(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["database"] in {"sqlite", "external"}
    assert isinstance(body["ideas"], int)


def test_dashboard_redirects_to_login(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login?next=")


def test_api_requires_a_session(client):
    response = client.get("/api/ideas")
    assert response.status_code == 401
    assert response.json()["detail"] == "Sign in to use this endpoint."

    response = client.post("/api/ideas/generate", json={"count": 10})
    assert response.status_code == 401


def test_static_assets_are_served(client):
    css = client.get("/static/app.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    assert "--accent" in css.text

    js = client.get("/static/app.js")
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]
    assert "data-clock-time" in js.text


def test_login_rejects_a_bad_password(client):
    response = client.post(
        "/login",
        data={"username": "tester", "password": "wrong", "next": "/"},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert "Wrong username or password." in response.text


def test_login_grants_access_and_pages_render(client):
    response = client.post(
        "/login",
        data={"username": "tester", "password": "test-password", "next": "/"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "sig_session" in client.cookies

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Generate ideas" in dashboard.text
    assert "data-clock-time" in dashboard.text
    assert "IST" in dashboard.text

    assert client.get("/history").status_code == 200
    assert client.get("/config").status_code == 200


def test_logout_clears_the_session(auth_client):
    response = auth_client.post("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert auth_client.get("/", follow_redirects=False).status_code == 303


def test_generate_without_a_key_explains_what_to_do(auth_client):
    response = auth_client.post(
        "/api/ideas/generate", json={"count": 10, "categories": [], "auto": True}
    )
    assert response.status_code == 400
    assert "No Hacker AI key saved" in response.json()["detail"]


def test_generate_rejects_unsupported_counts(auth_client):
    response = auth_client.post("/api/ideas/generate", json={"count": 7, "auto": True})
    assert response.status_code == 400
    assert "10, 20 or 50" in response.json()["detail"]


def test_voice_endpoint_without_an_elevenlabs_key(auth_client, db):
    from app.models import Idea

    idea = Idea(title="t", hook="h", script_hi="s", voiceover_text="भाषण " * 20)
    db.add(idea)
    db.commit()

    response = auth_client.post(f"/api/ideas/{idea.id}/voice", json={})
    assert response.status_code == 400
    assert "No ElevenLabs key saved" in response.json()["detail"]


def test_config_page_shows_a_hint_never_the_key(auth_client, db):
    store.set_secret(db, store.HACKER_AI_API_KEY, "sk-verysecretvalue9999")

    page = auth_client.get("/config")
    assert page.status_code == 200
    assert "sk-verysecretvalue9999" not in page.text
    assert "…9999" in page.text
    assert "encrypted" in page.text


def test_config_save_stores_and_clears_keys(auth_client, db):
    response = auth_client.post(
        "/config",
        data={
            "hacker_ai_api_key": "sk-saved-key-4242",
            "elevenlabs_api_key": "",
            "hacker_ai_model": "auto",
            "hacker_ai_base_url": "https://api.hackerai.sh/v1",
            "elevenlabs_voice_id": "CwhRBWXzGAHq8TQ4Fs17",
            "elevenlabs_model_id": "eleven_multilingual_v2",
            "default_speed": "1.0",
            "default_emotion": "energetic",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert store.get_secret(db, store.HACKER_AI_API_KEY) == "sk-saved-key-4242"

    clear = auth_client.post(
        "/config",
        data={
            "clear_hacker_ai": "1",
            "hacker_ai_model": "auto",
            "hacker_ai_base_url": "https://api.hackerai.sh/v1",
            "elevenlabs_voice_id": "CwhRBWXzGAHq8TQ4Fs17",
            "elevenlabs_model_id": "eleven_multilingual_v2",
            "default_speed": "1.0",
            "default_emotion": "energetic",
        },
        follow_redirects=False,
    )
    assert clear.status_code == 303
    assert store.get_secret(db, store.HACKER_AI_API_KEY) == ""


def test_elevenlabs_test_endpoint_without_a_key(auth_client):
    response = auth_client.post("/api/test/elevenlabs")
    assert response.status_code == 200
    assert response.json() == {"ok": False, "reason": "No ElevenLabs key saved."}


def test_unknown_api_path_returns_json_404(auth_client):
    response = auth_client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}


def test_meta_lists_all_twelve_categories(auth_client):
    response = auth_client.get("/api/meta")
    assert response.status_code == 200
    body = response.json()
    assert len(body["categories"]) == 12
    assert "Technology & AI" in body["categories"]
    assert "energetic" in body["emotions"]
