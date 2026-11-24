from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Idea(Base):
    __tablename__ = "ideas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True)

    title: Mapped[str] = mapped_column(String(240))
    hook: Mapped[str] = mapped_column(Text)
    script_hi: Mapped[str] = mapped_column(Text)
    scenes_json: Mapped[str] = mapped_column(Text, default="[]")
    voiceover_text: Mapped[str] = mapped_column(Text)
    emotion: Mapped[str] = mapped_column(String(32), default="energetic")
    music: Mapped[str] = mapped_column(String(200), default="")
    subtitles_json: Mapped[str] = mapped_column(Text, default="[]")
    description: Mapped[str] = mapped_column(Text, default="")
    hashtags_json: Mapped[str] = mapped_column(Text, default="[]")
    duration_sec: Mapped[int] = mapped_column(Integer, default=30)
    engagement_question: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(64), default="")
    provider: Mapped[str] = mapped_column(String(32), default="hackerai")
    model: Mapped[str] = mapped_column(String(64), default="auto")

    saved: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(24), default="active")  # active | replaced
    replaced_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)

    voiceovers: Mapped[list["Voiceover"]] = relationship(back_populates="idea", cascade="all, delete-orphan")

    @property
    def scenes(self) -> list[dict]:
        try:
            value = json.loads(self.scenes_json or "[]")
            return value if isinstance(value, list) else []
        except json.JSONDecodeError:
            return []

    @property
    def subtitles(self) -> list[str]:
        try:
            value = json.loads(self.subtitles_json or "[]")
            return [str(item) for item in value] if isinstance(value, list) else []
        except json.JSONDecodeError:
            return []

    @property
    def hashtags(self) -> list[str]:
        try:
            value = json.loads(self.hashtags_json or "[]")
            return [str(item) for item in value] if isinstance(value, list) else []
        except json.JSONDecodeError:
            return []

    def as_dict(self) -> dict:
        latest = self.voiceovers[-1] if self.voiceovers else None
        return {
            "id": self.id,
            "run_id": self.run_id,
            "title": self.title,
            "hook": self.hook,
            "script": self.script_hi,
            "scenes": self.scenes,
            "voiceover_text": self.voiceover_text,
            "emotion": self.emotion,
            "music": self.music,
            "subtitles": self.subtitles,
            "description": self.description,
            "hashtags": self.hashtags,
            "duration_sec": self.duration_sec,
            "engagement_question": self.engagement_question,
            "category": self.category,
            "saved": self.saved,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "voiceover_url": f"/voice/{latest.id}.mp3" if latest and latest.status == "ready" else None,
            "voiceover_download": f"/voice/{latest.id}/download" if latest and latest.status == "ready" else None,
        }


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    categories_json: Mapped[str] = mapped_column(Text, default="[]")
    auto: Mapped[bool] = mapped_column(Boolean, default=False)
    requested: Mapped[int] = mapped_column(Integer, default=10)
    generated: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="queued")  # queued|running|done|failed
    error: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(32), default="hackerai")
    model: Mapped[str] = mapped_column(String(64), default="auto")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def categories(self) -> list[str]:
        try:
            value = json.loads(self.categories_json or "[]")
            return [str(item) for item in value] if isinstance(value, list) else []
        except json.JSONDecodeError:
            return []


class Voiceover(Base):
    __tablename__ = "voiceovers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id", ondelete="CASCADE"), index=True)
    voice_id: Mapped[str] = mapped_column(String(64), default="")
    voice_name: Mapped[str] = mapped_column(String(120), default="")
    model_id: Mapped[str] = mapped_column(String(64), default="")
    emotion: Mapped[str] = mapped_column(String(32), default="")
    speed: Mapped[float] = mapped_column(Float, default=1.0)
    chars: Mapped[int] = mapped_column(Integer, default=0)
    bytes: Mapped[int] = mapped_column(Integer, default=0)
    path: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(24), default="ready")  # ready|failed
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)

    idea: Mapped[Idea] = relationship(back_populates="voiceovers")


class Secret(Base):
    __tablename__ = "secrets"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    hint: Mapped[str] = mapped_column(String(16), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
