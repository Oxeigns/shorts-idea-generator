"""Validate SKILL.md so the frontmatter can be auto-populated safely.

The manifest is read by tooling that expects YAML frontmatter between `---` fences with
at least a lowercase hyphenated `name` and a `description`. A malformed file would make
those fields empty, so the whole contract is asserted here.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "SKILL.md"

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _split() -> tuple[dict, str]:
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "SKILL.md must start with a YAML frontmatter fence"
    end = text.find("\n---\n", 4)
    assert end != -1, "frontmatter is not closed with a '---' line"
    front = text[:end].split("---\n", 1)[1]
    body = text[end + len("\n---\n") :]
    return yaml.safe_load(front), body


def test_skill_file_exists_at_project_root():
    assert SKILL.is_file(), "SKILL.md must ship at the repository root"


def test_frontmatter_parses_and_required_fields_are_present():
    data, _ = _split()
    assert isinstance(data, dict), "frontmatter must be a YAML mapping"

    name = data.get("name")
    description = data.get("description")
    assert isinstance(name, str) and name, "name is required"
    assert isinstance(description, str) and description.strip(), "description is required"


def test_name_is_a_valid_slug():
    data, _ = _split()
    name = data["name"]
    assert NAME_RE.match(name), f"{name!r} must be lowercase words separated by hyphens"
    assert 1 <= len(name) <= 64, "name must be 1-64 characters"


def test_description_is_usable_for_search():
    data, _ = _split()
    description = data["description"]
    assert len(description) <= 1024, "description must stay within 1024 characters"
    lowered = description.lower()
    # The description drives skill matching, so it must name the real triggers.
    for trigger in ("shorts", "hindi", "elevenlabs"):
        assert trigger in lowered, f"description should mention {trigger!r}"


def test_optional_fields_are_well_formed():
    data, _ = _split()

    version = data.get("version")
    assert version is None or SEMVER_RE.match(str(version)), "version must be semver"

    tools = data.get("allowed-tools")
    assert tools is None or isinstance(tools, str), "allowed-tools must be a space-separated string"
    if tools:
        assert "Read" in tools, "the skill needs Read access to inspect the project"

    metadata = data.get("metadata")
    assert isinstance(metadata, dict), "metadata must be a mapping"
    tags = metadata.get("tags")
    assert isinstance(tags, list) and tags, "metadata.tags must be a non-empty list"
    assert all(isinstance(tag, str) and tag for tag in tags)
    assert metadata.get("category"), "metadata.category is used for grouping"


def test_body_documents_the_real_contract():
    _, body = _split()
    assert len(body) > 1500, "the skill body must be substantive, not a stub"
    for heading in ("Quick start", "Troubleshooting", "Security rules"):
        assert heading in body, f"missing section: {heading}"
    # The two credentials are the most common failure; the body must warn about both.
    assert "hsb_" in body and "sk-" in body
    assert "Devanagari" in body


def test_manifest_never_contains_a_real_credential():
    text = SKILL.read_text(encoding="utf-8")
    assert not re.search(r"\bsk-[A-Za-z0-9_-]{24,}", text)
    assert not re.search(r"\bhsb_[A-Za-z0-9]{24,}", text)
    assert not re.search(r"\bsk_[a-f0-9]{40,}\b", text)
