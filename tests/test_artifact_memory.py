"""Tests for Phase γ-4: Structured Artifact Memory."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mind.kernel.schema import (
    CORE_OBJECT_TYPES,
    REQUIRED_METADATA_FIELDS,
    ensure_valid_object,
    validate_object,
)
from mind.offline.artifact_indexer import build_artifact_index
from mind.offline_jobs import OfflineJobKind, RebuildArtifactIndexJobPayload


def _ts() -> str:
    return datetime.now(UTC).isoformat()


def _long_object(content: str = "", obj_id: str = "long-obj-1") -> dict:
    if not content:
        content = "\n".join(
            [
                "# Introduction",
                "This section introduces the topic with detailed background information.",
                "More content about the introduction.",
                "",
                "## Background",
                "Background details about the subject matter.",
                "Additional context and history.",
                "",
                "## Methodology",
                "The methodology used in this study is described here.",
                "Multiple steps were followed to ensure accuracy.",
                "",
                "# Results",
                "Results section containing numerical and qualitative findings.",
                "Discussion of what was found.",
            ]
        )
    return {
        "id": obj_id,
        "type": "SummaryNote",
        "content": content,
        "source_refs": ["ep-1"],
        "created_at": _ts(),
        "updated_at": _ts(),
        "version": 1,
        "status": "active",
        "priority": 0.7,
        "metadata": {
            "summary_scope": "document",
            "input_refs": ["ep-1"],
            "compression_ratio_estimate": 0.3,
        },
    }


# ─── Schema ──────────────────────────────────────────────────────────────────


class TestArtifactIndexSchema:
    def test_artifact_index_in_core_types(self) -> None:
        assert "ArtifactIndex" in CORE_OBJECT_TYPES

    def test_artifact_index_required_metadata(self) -> None:
        fields = REQUIRED_METADATA_FIELDS["ArtifactIndex"]
        assert "parent_object_id" in fields
        assert "section_id" in fields
        assert "heading" in fields
        assert "summary" in fields
        assert "depth" in fields
        assert "content_range" in fields

    def test_valid_artifact_index_object(self) -> None:
        obj = {
            "id": "artifact-1",
            "type": "ArtifactIndex",
            "content": {"summary": "intro section", "heading": "Introduction"},
            "source_refs": ["parent-doc-1"],
            "created_at": _ts(),
            "updated_at": _ts(),
            "version": 1,
            "status": "active",
            "priority": 0.5,
            "metadata": {
                "parent_object_id": "parent-doc-1",
                "section_id": "section-1",
                "heading": "Introduction",
                "summary": "intro section",
                "depth": 1,
                "content_range": {"start": 0, "end": 200},
            },
        }
        assert validate_object(obj) == []

    def test_invalid_depth(self) -> None:
        obj = {
            "id": "artifact-2",
            "type": "ArtifactIndex",
            "content": {"summary": "x", "heading": "Y"},
            "source_refs": ["parent-1"],
            "created_at": _ts(),
            "updated_at": _ts(),
            "version": 1,
            "status": "active",
            "priority": 0.5,
            "metadata": {
                "parent_object_id": "parent-1",
                "section_id": "s-1",
                "heading": "Y",
                "summary": "x",
                "depth": -1,
                "content_range": {"start": 0, "end": 100},
            },
        }
        errors = validate_object(obj)
        assert any("depth" in e for e in errors)

    def test_invalid_content_range_type(self) -> None:
        obj = {
            "id": "artifact-3",
            "type": "ArtifactIndex",
            "content": {"summary": "x", "heading": "Y"},
            "source_refs": ["parent-1"],
            "created_at": _ts(),
            "updated_at": _ts(),
            "version": 1,
            "status": "active",
            "priority": 0.5,
            "metadata": {
                "parent_object_id": "parent-1",
                "section_id": "s-1",
                "heading": "Y",
                "summary": "x",
                "depth": 0,
                "content_range": "invalid",
            },
        }
        errors = validate_object(obj)
        assert any("content_range" in e for e in errors)


# ─── build_artifact_index ────────────────────────────────────────────────────


class TestBuildArtifactIndex:
    def test_short_content_returns_empty(self) -> None:
        obj = _long_object(content="short", obj_id="short-1")
        result = build_artifact_index(obj, min_content_length=500)
        assert result == []

    def test_long_content_returns_sections(self) -> None:
        obj = _long_object()
        result = build_artifact_index(obj, min_content_length=50)
        assert len(result) > 0

    def test_all_results_are_artifact_index_type(self) -> None:
        obj = _long_object()
        result = build_artifact_index(obj, min_content_length=50)
        assert all(item["type"] == "ArtifactIndex" for item in result)

    def test_all_results_pass_schema_validation(self) -> None:
        obj = _long_object()
        result = build_artifact_index(obj, min_content_length=50)
        for item in result:
            errors = validate_object(item)
            assert errors == [], f"Validation errors: {errors}"

    def test_parent_object_id_set_correctly(self) -> None:
        obj = _long_object(obj_id="parent-doc-42")
        result = build_artifact_index(obj, min_content_length=50)
        for item in result:
            assert item["metadata"]["parent_object_id"] == "parent-doc-42"

    def test_source_refs_point_to_parent(self) -> None:
        obj = _long_object(obj_id="parent-doc-43")
        result = build_artifact_index(obj, min_content_length=50)
        for item in result:
            assert "parent-doc-43" in item["source_refs"]

    def test_no_headings_creates_root_section(self) -> None:
        long_text = "A" * 600
        obj = _long_object(content=long_text, obj_id="no-headings")
        result = build_artifact_index(obj, min_content_length=100)
        assert len(result) == 1
        assert result[0]["metadata"]["heading"] == "(root)"
        assert result[0]["metadata"]["depth"] == 0

    def test_headings_create_multiple_sections(self) -> None:
        content = (
            "# Section One\n" + "content " * 50 + "\n"
            "## Sub-section\n" + "sub content " * 30 + "\n"
            "# Section Two\n" + "more content " * 40 + "\n"
        )
        obj = _long_object(content=content, obj_id="with-headings")
        result = build_artifact_index(obj, min_content_length=50)
        assert len(result) >= 3

    def test_section_ids_unique(self) -> None:
        obj = _long_object()
        result = build_artifact_index(obj, min_content_length=50)
        section_ids = [item["metadata"]["section_id"] for item in result]
        assert len(section_ids) == len(set(section_ids))

    def test_object_ids_unique(self) -> None:
        obj = _long_object()
        result = build_artifact_index(obj, min_content_length=50)
        obj_ids = [item["id"] for item in result]
        assert len(obj_ids) == len(set(obj_ids))

    def test_content_range_bounds(self) -> None:
        obj = _long_object()
        result = build_artifact_index(obj, min_content_length=50)
        for item in result:
            cr = item["metadata"]["content_range"]
            assert cr["start"] >= 0
            assert cr["end"] > cr["start"]

    def test_workspaceview_not_indexed(self) -> None:
        """WorkspaceView objects should not be indexed (caller responsibility)."""
        content = "W" * 600
        obj = {
            "id": "ws-1",
            "type": "WorkspaceView",
            "content": {"purpose": content},
            "source_refs": ["src-1"],
            "created_at": _ts(),
            "updated_at": _ts(),
            "version": 1,
            "status": "active",
            "priority": 0.5,
            "metadata": {
                "task_id": "task-1",
                "slot_limit": 4,
                "slots": [],
                "selection_policy": "retrieval-score-then-priority",
            },
        }
        # build_artifact_index just extracts text from content; the caller
        # (offline service) filters out WorkspaceView/ArtifactIndex objects.
        # Here we verify the extractor doesn't crash.
        result = build_artifact_index(obj, min_content_length=50)
        # WorkspaceView content is a dict; artifact indexer should handle it.
        # (len check is implementation-defined — just no exception)
        assert isinstance(result, list)


# ─── Offline job kinds ────────────────────────────────────────────────────────


class TestArtifactJobKinds:
    def test_rebuild_artifact_index_kind_exists(self) -> None:
        assert OfflineJobKind.REBUILD_ARTIFACT_INDEX == "rebuild_artifact_index"

    def test_rebuild_artifact_index_payload(self) -> None:
        payload = RebuildArtifactIndexJobPayload(
            object_ids=["obj-1"],
            min_content_length=1000,
        )
        assert payload.min_content_length == 1000
