from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# A checked-out .env should behave the way operators expect. Real environment
# variables always win, so a shell export or host dashboard setting is never
# overwritten by the file.
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is a declared dependency
    load_dotenv = None  # type: ignore[assignment]

if load_dotenv is not None:
    load_dotenv(BASE_DIR / ".env", override=False)


def _bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


class Settings:
    """Environment-backed configuration.

    The encryption key is read from APP_SECRET_KEY, or generated once and kept in
    ``data/secret.key`` (0600) so encrypted API keys survive a restart without the
    operator having to invent a secret.
    """

    def __init__(self) -> None:
        self.base_dir = BASE_DIR
        self.data_dir = Path(os.getenv("DATA_DIR") or (BASE_DIR / "data"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.voice_dir = self.data_dir / "voiceovers"
        self.voice_dir.mkdir(parents=True, exist_ok=True)

        self.db_url = os.getenv("DATABASE_URL") or f"sqlite:///{self.data_dir / 'ideas.db'}"
        self.secret_key = self._secret_key()

        self.admin_username = os.getenv("ADMIN_USERNAME") or "admin"
        self.admin_password = os.getenv("ADMIN_PASSWORD") or "change-this-password"
        self.cookie_name = "sig_session"
        self.session_days = int(os.getenv("SESSION_DAYS") or 7)

        self.hackerai_api_key = (os.getenv("HACKER_AI_API_KEY") or os.getenv("HACKERAI_API_KEY") or "").strip()
        self.hackerai_base_url = (os.getenv("HACKER_AI_BASE_URL") or "https://api.hackerai.sh/v1").rstrip("/")
        self.hackerai_model = os.getenv("HACKER_AI_MODEL") or "auto"

        self.elevenlabs_api_key = (os.getenv("ELEVENLABS_API_KEY") or "").strip()
        self.elevenlabs_voice_id = os.getenv("ELEVENLABS_VOICE_ID") or "CwhRBWXzGAHq8TQ4Fs17"
        self.elevenlabs_model_id = os.getenv("ELEVENLABS_MODEL_ID") or "eleven_multilingual_v2"

        self.request_timeout = float(os.getenv("REQUEST_TIMEOUT") or 90)
        self.allow_env_secrets = _bool("ALLOW_ENV_SECRETS", True)
        # Opt-in escape hatch for a local Hacker AI-compatible gateway.
        self.allow_insecure_base_url = _bool("HACKER_AI_ALLOW_INSECURE_BASE_URL", False)
        self.security_headers = _bool("SECURITY_HEADERS", True)
        # HSTS is only emitted for HTTPS requests; set to 0 to disable it entirely.
        self.hsts = _bool("HSTS", True)

    def _secret_key(self) -> str:
        from_env = (os.getenv("APP_SECRET_KEY") or "").strip()
        if from_env:
            return from_env
        path = self.data_dir / "secret.key"
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        value = secrets.token_hex(32)
        path.write_text(value, encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return value


settings = Settings()
