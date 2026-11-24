"""Guard: the repository must never contain a live credential.

The bridge token and the inference key are both long random strings. A single
accidental paste into a tracked file would publish a working credential, so the
suite fails if one ever appears. Only files that ship in the repository are
scanned — .env, data/ and .venv are git-ignored.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Keys and bridge tokens are long, high-entropy strings after a known prefix.
PATTERNS = {
    "hackerai inference key": re.compile(r"\bsk-[A-Za-z0-9_-]{24,}"),
    "hackerai bridge token": re.compile(r"\bhsb_[A-Za-z0-9]{24,}"),
    "elevenlabs key": re.compile(r"\bsk_[a-f0-9]{40,}\b"),
}

SKIP_DIRS = {".git", ".venv", "venv", "data", "__pycache__", ".pytest_cache"}
SKIP_FILES = {".env"}
SCANNED_SUFFIXES = {".py", ".md", ".sh", ".html", ".css", ".js", ".txt", ".example", ".yaml", ".yml", ".toml"}


def _files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in SKIP_FILES:
            continue
        if path.suffix not in SCANNED_SUFFIXES and path.name != ".gitignore":
            continue
        yield path


def test_repository_contains_no_live_credentials():
    findings = []
    for path in _files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:  # pragma: no cover - unreadable file
            continue
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                findings.append(f"{path.relative_to(ROOT)}: {label} ({match.group(0)[:6]}…)")

    assert not findings, "Live credential(s) found in tracked files:\n" + "\n".join(findings)


def test_env_template_keeps_secret_fields_empty():
    template = (ROOT / ".env.example").read_text(encoding="utf-8")
    for line in template.splitlines():
        stripped = line.strip()
        if stripped.startswith(("HACKER_AI_API_KEY=", "ELEVENLABS_API_KEY=", "HACKERAI_BRIDGE_TOKEN=")):
            value = stripped.split("=", 1)[1].strip()
            assert value == "", f"{stripped.split('=')[0]} must not ship a value"


def test_bridge_script_does_not_hardcode_a_token():
    script = (ROOT / "bridge.sh").read_text(encoding="utf-8")
    # The script legitimately mentions the "hsb_" prefix in its help text, so look
    # for a complete high-entropy token instead of the prefix alone.
    assert not re.search(r"hsb_[A-Za-z0-9]{24,}", script), "bridge.sh must not embed a token"
    assert "HACKERAI_BRIDGE_TOKEN" in script, "the script must read the token from the environment"
    # The token must be quoted so an odd value cannot become several arguments.
    assert '--token "$TOKEN"' in script, "the token must be passed quoted"


def test_gitignore_covers_secrets_and_runtime_data():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    entries = {line.strip() for line in ignore if line.strip() and not line.startswith("#")}
    for required in {".env", "data/"}:
        assert required in entries, f".gitignore must ignore {required}"
    assert "!.env.example" in entries, ".env.example must stay tracked as the template"
