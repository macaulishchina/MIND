"""Structured artifact memory indexer (Phase γ-4).

Builds a tree-shaped :data:`ArtifactIndex` object hierarchy for long objects
(e.g. long documents, large episodes) so that retrieval can navigate from a
high-level section summary down to the raw content.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

#: Minimum content length (characters) before an object is eligible for indexing.
DEFAULT_MIN_CONTENT_LENGTH = 500

#: Regex for detecting Markdown-style headings in string content.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _extract_sections(text: str) -> list[dict[str, Any]]:
    """Split *text* on Markdown headings and return section dicts."""
    sections: list[dict[str, Any]] = []
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        # No headings — treat the whole text as one section.
        return [
            {
                "section_id": "section-1",
                "heading": "(root)",
                "depth": 0,
                "parent_section_id": None,
                "content_range": {"start": 0, "end": len(text)},
                "summary": text[:200].strip(),
            }
        ]

    for i, match in enumerate(matches):
        depth = len(match.group(1))
        heading = match.group(2).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        snippet = text[start:end].strip()
        parent_depth = depth - 1
        parent_section_id: str | None = None
        # Walk backwards to find the most recent section at parent_depth.
        for prev in reversed(sections):
            if prev["depth"] == parent_depth:
                parent_section_id = prev["section_id"]
                break
        sections.append(
            {
                "section_id": f"section-{i + 1}",
                "heading": heading,
                "depth": depth,
                "parent_section_id": parent_section_id,
                "content_range": {"start": start, "end": end},
                "summary": snippet[:200].strip(),
            }
        )
    return sections


def _content_text(obj: dict[str, Any]) -> str:
    content = obj.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        for key in ("text", "summary", "body", "result", "title"):
            val = content.get(key)
            if isinstance(val, str):
                return val
        import json

        return json.dumps(content, ensure_ascii=False)
    return str(content)


def build_artifact_index(
    obj: dict[str, Any],
    *,
    min_content_length: int = DEFAULT_MIN_CONTENT_LENGTH,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return a list of ArtifactIndex objects for *obj*.

    Returns an empty list when the object is too short or not eligible for
    indexing.  Each returned object is a fully-valid MIND object ready to be
    written to the store.

    Args:
        obj: The source memory object (any type with a text/dict ``content``).
        min_content_length: Minimum character length before indexing is applied.
        now: Optional timestamp override (defaults to UTC now).

    Returns:
        List of ArtifactIndex objects (may be empty).
    """
    text = _content_text(obj)
    if len(text) < min_content_length:
        return []

    ts = (now or _utc_now()).isoformat()
    sections = _extract_sections(text)
    parent_object_id = obj["id"]
    index_objects: list[dict[str, Any]] = []
    for section in sections:
        artifact_id = f"artifact-{parent_object_id}-{section['section_id']}-{uuid4().hex[:8]}"
        index_objects.append(
            {
                "id": artifact_id,
                "type": "ArtifactIndex",
                "content": {
                    "summary": section["summary"],
                    "heading": section["heading"],
                },
                "source_refs": [parent_object_id],
                "created_at": ts,
                "updated_at": ts,
                "version": 1,
                "status": "active",
                "priority": float(obj.get("priority", 0.5)),
                "metadata": {
                    "parent_object_id": parent_object_id,
                    "section_id": section["section_id"],
                    "heading": section["heading"],
                    "summary": section["summary"],
                    "depth": section["depth"],
                    "content_range": section["content_range"],
                    "parent_section_id": section["parent_section_id"],
                },
            }
        )
    return index_objects
