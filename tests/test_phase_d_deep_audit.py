"""Supplementary tests added during Phase D deep audit.

Covers edge cases and gaps identified in design review:
- WorkspaceBuilder edge cases (all-invalid, slot_limit > candidates, dedup, errors)
- Retrieval module (multi-mode, empty query, open-ended time windows, embedding edges)
- Context protocol (empty object_ids, workspace context determinism)
- Answer scoring (empty answer, empty fragments, faithfulness zero)
- cosine_similarity dimension mismatch, embed_text empty
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from mind.fixtures.golden_episode_set import build_core_object_showcase, build_golden_episode_set
from mind.kernel.retrieval import (
    build_query_embedding,
    build_search_text,
    cosine_similarity,
    embed_text,
    keyword_score,
    search_objects,
    time_window_score,
    tokenize,
    vector_score,
)
from mind.kernel.schema import validate_object
from mind.kernel.store import MemoryStore, SQLiteMemoryStore
from mind.primitives.contracts import (
    PrimitiveExecutionContext,
    PrimitiveOutcome,
    RetrieveQueryMode,
    RetrieveResponse,
)
from mind.primitives.service import PrimitiveService
from mind.workspace.answer_benchmark import (
    GeneratedAnswer,
    answer_from_workspace,
    score_answer,
)
from mind.workspace.builder import WorkspaceBuilder, WorkspaceBuildError
from mind.workspace.context_protocol import (
    WORKSPACE_CONTEXT_PROTOCOL,
    build_raw_topk_context,
    build_workspace_context,
)

FIXED_TIMESTAMP = datetime(2026, 3, 9, 16, 0, tzinfo=UTC)


def _context() -> PrimitiveExecutionContext:
    return PrimitiveExecutionContext(
        actor="deep_audit_test",
        budget_scope_id="deep_audit::1",
    )


# ---------------------------------------------------------------------------
# WorkspaceBuilder edge cases
# ---------------------------------------------------------------------------


class TestWorkspaceBuilderEdgeCases:
    """Edge-case coverage for WorkspaceBuilder.build()."""

    def test_all_candidates_invalid_raises_error(self, tmp_path: Path) -> None:
        """When every candidate has status='invalid', build must raise."""
        db_path = tmp_path / "all_invalid.sqlite3"
        showcase = build_core_object_showcase()
        invalid_obj: dict[str, Any] = {
            "id": "only-invalid",
            "type": "SummaryNote",
            "content": {"summary": "I am invalid"},
            "source_refs": [showcase[0]["id"]],
            "created_at": FIXED_TIMESTAMP.isoformat(),
            "updated_at": FIXED_TIMESTAMP.isoformat(),
            "version": 1,
            "status": "invalid",
            "priority": 0.5,
            "metadata": {
                "summary_scope": "episode",
                "input_refs": [showcase[0]["id"]],
                "compression_ratio_estimate": 0.5,
            },
        }
        with SQLiteMemoryStore(db_path) as store:
            store.insert_objects(showcase)
            store.insert_object(invalid_obj)
            builder = WorkspaceBuilder(store, clock=lambda: FIXED_TIMESTAMP)
            with pytest.raises(WorkspaceBuildError, match="no accessible candidates"):
                builder.build(
                    task_id="test-task",
                    candidate_ids=["only-invalid"],
                    slot_limit=2,
                )

    def test_slot_limit_exceeds_candidate_count(self, tmp_path: Path) -> None:
        """slot_limit=10 with 2 candidates should select both without error."""
        db_path = tmp_path / "excess_slots.sqlite3"
        showcase = build_core_object_showcase()
        with SQLiteMemoryStore(db_path) as store:
            store.insert_objects(showcase)
            builder = WorkspaceBuilder(store, clock=lambda: FIXED_TIMESTAMP)
            result = builder.build(
                task_id="showcase-task",
                candidate_ids=[showcase[2]["id"], showcase[3]["id"]],
                candidate_scores=[0.9, 0.4],
                slot_limit=10,
            )
        assert len(result.selected_ids) == 2
        assert len(result.workspace["metadata"]["slots"]) == 2
        assert validate_object(result.workspace) == []

    def test_deduplication_keeps_highest_score(self, tmp_path: Path) -> None:
        """When same candidate appears twice, keep the higher score."""
        db_path = tmp_path / "dedup.sqlite3"
        showcase = build_core_object_showcase()
        with SQLiteMemoryStore(db_path) as store:
            store.insert_objects(showcase)
            builder = WorkspaceBuilder(store, clock=lambda: FIXED_TIMESTAMP)
            result = builder.build(
                task_id="showcase-task",
                candidate_ids=[showcase[2]["id"], showcase[2]["id"], showcase[3]["id"]],
                candidate_scores=[0.3, 0.9, 0.5],
                slot_limit=2,
            )
        # showcase[2] should have score 0.9 (dedup kept max),
        # so it ranks above showcase[3] at 0.5
        assert result.selected_ids[0] == showcase[2]["id"]

    def test_empty_task_id_raises_error(self, tmp_path: Path) -> None:
        db_path = tmp_path / "empty_task.sqlite3"
        showcase = build_core_object_showcase()
        with SQLiteMemoryStore(db_path) as store:
            store.insert_objects(showcase)
            builder = WorkspaceBuilder(store, clock=lambda: FIXED_TIMESTAMP)
            with pytest.raises(WorkspaceBuildError, match="task_id must be non-empty"):
                builder.build(
                    task_id="",
                    candidate_ids=[showcase[2]["id"]],
                    slot_limit=1,
                )

    def test_empty_candidate_ids_raises_error(self, tmp_path: Path) -> None:
        db_path = tmp_path / "empty_candidates.sqlite3"
        showcase = build_core_object_showcase()
        with SQLiteMemoryStore(db_path) as store:
            store.insert_objects(showcase)
            builder = WorkspaceBuilder(store, clock=lambda: FIXED_TIMESTAMP)
            with pytest.raises(WorkspaceBuildError, match="candidate_ids must be non-empty"):
                builder.build(
                    task_id="test-task",
                    candidate_ids=[],
                    slot_limit=1,
                )

    def test_misaligned_scores_raises_error(self, tmp_path: Path) -> None:
        db_path = tmp_path / "misaligned.sqlite3"
        showcase = build_core_object_showcase()
        with SQLiteMemoryStore(db_path) as store:
            store.insert_objects(showcase)
            builder = WorkspaceBuilder(store, clock=lambda: FIXED_TIMESTAMP)
            with pytest.raises(WorkspaceBuildError, match="candidate_scores must align"):
                builder.build(
                    task_id="test-task",
                    candidate_ids=[showcase[2]["id"]],
                    candidate_scores=[0.9, 0.5],
                    slot_limit=1,
                )

    def test_missing_candidate_raises_error(self, tmp_path: Path) -> None:
        db_path = tmp_path / "missing.sqlite3"
        showcase = build_core_object_showcase()
        with SQLiteMemoryStore(db_path) as store:
            store.insert_objects(showcase)
            builder = WorkspaceBuilder(store, clock=lambda: FIXED_TIMESTAMP)
            with pytest.raises(WorkspaceBuildError, match="not found"):
                builder.build(
                    task_id="test-task",
                    candidate_ids=["nonexistent-object"],
                    slot_limit=1,
                )

    def test_workspace_source_refs_match_selected_ids(self, tmp_path: Path) -> None:
        """The workspace object's source_refs must equal selected_ids."""
        db_path = tmp_path / "source_refs.sqlite3"
        showcase = build_core_object_showcase()
        with SQLiteMemoryStore(db_path) as store:
            store.insert_objects(showcase)
            builder = WorkspaceBuilder(store, clock=lambda: FIXED_TIMESTAMP)
            result = builder.build(
                task_id="showcase-task",
                candidate_ids=[showcase[2]["id"], showcase[3]["id"]],
                candidate_scores=[0.9, 0.4],
                slot_limit=4,
            )
        assert result.workspace["source_refs"] == list(result.selected_ids)
        assert result.workspace["content"]["selected_object_ids"] == list(result.selected_ids)


# ---------------------------------------------------------------------------
# Retrieval module edge cases
# ---------------------------------------------------------------------------


class TestRetrievalEdgeCases:
    """Edge-case coverage for retrieval scoring functions."""

    def test_keyword_score_empty_query_returns_zero(self) -> None:
        showcase = build_core_object_showcase()
        assert keyword_score("", showcase[0]) == 0.0

    def test_keyword_score_no_overlap_returns_zero(self) -> None:
        showcase = build_core_object_showcase()
        assert keyword_score("zzzzzzzzuniquenonmatch", showcase[0]) == 0.0

    def test_time_window_open_start_only(self) -> None:
        """Only end bound — objects before end should match."""
        obj: dict[str, Any] = {
            "id": "tw-test",
            "type": "RawRecord",
            "content": {"text": "hello"},
            "source_refs": [],
            "created_at": "2026-01-01T05:00:00+00:00",
            "updated_at": "2026-01-01T05:00:00+00:00",
            "version": 1,
            "status": "active",
            "priority": 0.5,
            "metadata": {"episode_id": "e1", "record_kind": "user_message", "timestamp_order": 0},
        }
        assert time_window_score({"end": "2026-01-01T06:00:00+00:00"}, obj) == 1.0
        assert time_window_score({"end": "2026-01-01T04:00:00+00:00"}, obj) == 0.0

    def test_time_window_open_end_only(self) -> None:
        """Only start bound — objects after start should match."""
        obj: dict[str, Any] = {
            "id": "tw-test",
            "type": "RawRecord",
            "content": {"text": "hello"},
            "source_refs": [],
            "created_at": "2026-01-01T05:00:00+00:00",
            "updated_at": "2026-01-01T05:00:00+00:00",
            "version": 1,
            "status": "active",
            "priority": 0.5,
            "metadata": {"episode_id": "e1", "record_kind": "user_message", "timestamp_order": 0},
        }
        assert time_window_score({"start": "2026-01-01T04:00:00+00:00"}, obj) == 1.0
        assert time_window_score({"start": "2026-01-01T06:00:00+00:00"}, obj) == 0.0

    def test_time_window_string_query_returns_zero(self) -> None:
        obj = build_core_object_showcase()[0]
        assert time_window_score("not a dict", obj) == 0.0

    def test_time_window_no_bounds_returns_zero(self) -> None:
        obj = build_core_object_showcase()[0]
        assert time_window_score({}, obj) == 0.0

    def test_embed_text_empty_string_returns_zero_vector(self) -> None:
        result = embed_text("")
        assert len(result) == 64
        assert all(v == 0.0 for v in result)

    def test_embed_text_deterministic(self) -> None:
        a = embed_text("hello world test")
        b = embed_text("hello world test")
        assert a == b

    def test_embed_text_normalized(self) -> None:
        import math

        result = embed_text("test normalization vector")
        norm = math.sqrt(sum(v * v for v in result))
        assert abs(norm - 1.0) < 1e-4

    def test_cosine_similarity_identical_vectors(self) -> None:
        v = embed_text("test vector")
        sim = cosine_similarity(v, v)
        assert abs(sim - 1.0) < 1e-5

    def test_cosine_similarity_empty_vectors(self) -> None:
        assert cosine_similarity((), ()) == 0.0
        assert cosine_similarity((), (1.0, 2.0)) == 0.0
        assert cosine_similarity((1.0, 2.0), ()) == 0.0

    def test_cosine_similarity_dimension_mismatch_raises(self) -> None:
        """After fix, mismatched dimensions should raise ValueError."""
        with pytest.raises(ValueError):
            cosine_similarity((1.0, 0.0), (0.0, 1.0, 0.0))

    def test_vector_score_none_embedding_returns_zero(self) -> None:
        obj = build_core_object_showcase()[0]
        assert vector_score(None, obj) == 0.0

    def test_build_search_text_contains_id_and_type(self) -> None:
        showcase = build_core_object_showcase()
        text = build_search_text(showcase[0])
        assert showcase[0]["id"].lower() in text
        assert showcase[0]["type"].lower() in text

    def test_build_search_text_excludes_reserved_control_plane_metadata(self) -> None:
        obj = build_core_object_showcase()[2]
        obj["metadata"] = dict(obj["metadata"])
        obj["metadata"]["provenance_id"] = "prov-001"
        obj["metadata"]["governance_plan"] = {"scope": "memory_world"}

        text = build_search_text(obj)

        assert "prov-001" not in text
        assert "governance_plan" not in text
        assert "summary_scope" in text

    def test_build_search_text_keeps_cjk_content_readable(self) -> None:
        obj = build_core_object_showcase()[0]
        obj["content"] = "你好，今天下雨，记得带伞。"

        text = build_search_text(obj)

        assert "你好" in text
        assert "\\u4f60" not in text

    def test_tokenize_basic(self) -> None:
        result = tokenize("Hello World 123")
        assert result == {"hello", "world", "123"}

    def test_tokenize_supports_cjk_keywords(self) -> None:
        result = tokenize("你好，今天下雨")
        assert "你好" in result
        assert "今天下雨" in result
        assert "今天" in result
        assert "下雨" in result

    def test_tokenize_empty(self) -> None:
        assert tokenize("") == set()
        assert tokenize("   ") == set()

    def test_multi_mode_keyword_plus_vector_scoring(self, tmp_path: Path) -> None:
        """Combined KEYWORD+VECTOR scoring produces higher scores than either alone."""
        db_path = tmp_path / "multi_mode.sqlite3"
        showcase = build_core_object_showcase()
        with SQLiteMemoryStore(db_path) as store:
            store.insert_objects(showcase)
            all_objects = store.iter_objects()

        query = "showcase summary"
        query_emb = build_query_embedding(query)

        keyword_only = search_objects(
            all_objects,
            query=query,
            query_modes=[RetrieveQueryMode.KEYWORD],
            max_candidates=5,
            object_types=["SummaryNote"],
            statuses=[],
            episode_id=None,
            task_id=None,
            query_embedding=None,
        )
        combined = search_objects(
            all_objects,
            query=query,
            query_modes=[RetrieveQueryMode.KEYWORD, RetrieveQueryMode.VECTOR],
            max_candidates=5,
            object_types=["SummaryNote"],
            statuses=[],
            episode_id=None,
            task_id=None,
            query_embedding=query_emb,
        )

        assert len(keyword_only) > 0
        assert len(combined) > 0
        # Combined should have higher or equal top score than keyword-only
        assert combined[0].score >= keyword_only[0].score

    def test_multi_mode_keyword_plus_time_window(self, tmp_path: Path) -> None:
        """KEYWORD+TIME_WINDOW scores add up correctly."""
        db_path = tmp_path / "multi_kw_tw.sqlite3"
        showcase = build_core_object_showcase()
        with SQLiteMemoryStore(db_path) as store:
            store.insert_objects(showcase)
            all_objects = store.iter_objects()

        # Query both keyword-matching and time-matching
        query: dict[str, Any] = {
            "start": "2026-01-01T00:00:00+00:00",
            "end": "2026-01-01T00:02:00+00:00",
        }
        results = search_objects(
            all_objects,
            query=query,
            query_modes=[RetrieveQueryMode.KEYWORD, RetrieveQueryMode.TIME_WINDOW],
            max_candidates=10,
            object_types=[],
            statuses=[],
            episode_id=None,
            task_id=None,
            query_embedding=None,
        )
        # At least some objects should be in the time window
        assert len(results) > 0


# ---------------------------------------------------------------------------
# Context protocol edge cases
# ---------------------------------------------------------------------------


class TestContextProtocolEdgeCases:
    """Edge cases for context serialization protocol."""

    def test_build_raw_topk_context_empty_ids(self, tmp_path: Path) -> None:
        """Empty object_ids should produce valid but empty context."""
        db_path = tmp_path / "empty_ctx.sqlite3"
        showcase = build_core_object_showcase()
        with SQLiteMemoryStore(db_path) as store:
            store.insert_objects(showcase)
            ctx = build_raw_topk_context(store, ())

        assert ctx.protocol == WORKSPACE_CONTEXT_PROTOCOL
        assert ctx.kind == "raw_topk"
        assert ctx.object_ids == ()
        payload = json.loads(ctx.text)
        assert payload["objects"] == []

    def test_workspace_context_deterministic(self, tmp_path: Path) -> None:
        """Calling build_workspace_context twice on same workspace produces same output."""
        db_path = tmp_path / "ws_det.sqlite3"
        showcase = build_core_object_showcase()
        with SQLiteMemoryStore(db_path) as store:
            store.insert_objects(showcase)
            builder = WorkspaceBuilder(store, clock=lambda: FIXED_TIMESTAMP)
            result = builder.build(
                task_id="showcase-task",
                candidate_ids=[showcase[2]["id"]],
                slot_limit=1,
            )
        ctx1 = build_workspace_context(result.workspace)
        ctx2 = build_workspace_context(result.workspace)
        assert ctx1.text == ctx2.text
        assert ctx1.token_count == ctx2.token_count

    def test_raw_topk_context_excludes_reserved_control_plane_metadata(
        self,
    ) -> None:
        class FakeStore:
            def read_object(self, object_id: str) -> dict[str, Any]:
                assert object_id == "raw-control-plane"
                return {
                    "id": "raw-control-plane",
                    "type": "RawRecord",
                    "content": {"text": "hello"},
                    "source_refs": [],
                    "metadata": {
                        "episode_id": "e1",
                        "record_kind": "user_message",
                        "timestamp_order": 1,
                        "provenance_id": "prov-001",
                    },
                }

        ctx = build_raw_topk_context(
            cast(MemoryStore, FakeStore()),
            ("raw-control-plane",),
        )

        payload = json.loads(ctx.text)
        assert payload["objects"][0]["metadata"]["episode_id"] == "e1"
        assert "provenance_id" not in payload["objects"][0]["metadata"]


# ---------------------------------------------------------------------------
# Answer scoring edge cases
# ---------------------------------------------------------------------------


class TestAnswerScoringEdgeCases:
    """Edge cases for score_answer and related functions."""

    def test_score_answer_empty_answer_text(self) -> None:
        """Empty answer should get low scores."""
        from mind.fixtures.episode_answer_bench import AnswerKind, EpisodeAnswerBenchCase

        case = EpisodeAnswerBenchCase(
            case_id="test_empty",
            task_id="task-001",
            episode_id="episode-001",
            prompt="What was the result?",
            answer_kind=AnswerKind.SUMMARY,
            required_fragments=("success",),
            gold_fact_ids=("episode-001",),
            gold_memory_refs=("episode-001",),
            max_answer_tokens=10,
        )
        answer = GeneratedAnswer(text="", support_ids=())
        score = score_answer(case, answer)

        assert score.task_completion_score == 0.0
        assert not score.task_success
        assert score.answer_quality_score < 0.5  # Should be low

    def test_score_answer_empty_required_fragments_no_crash(self) -> None:
        """Empty required_fragments should not cause ZeroDivisionError."""
        from mind.fixtures.episode_answer_bench import AnswerKind, EpisodeAnswerBenchCase

        case = EpisodeAnswerBenchCase(
            case_id="test_no_frags",
            task_id="task-001",
            episode_id="episode-001",
            prompt="What?",
            answer_kind=AnswerKind.SUMMARY,
            required_fragments=(),
            gold_fact_ids=("episode-001",),
            gold_memory_refs=("episode-001",),
            max_answer_tokens=10,
        )
        answer = GeneratedAnswer(text="some answer", support_ids=("episode-001",))
        score = score_answer(case, answer)

        assert score.task_completion_score == 0.0  # 0 fragments matched / 0 → guarded to 0.0
        assert isinstance(score.answer_quality_score, float)

    def test_score_answer_perfect_match(self) -> None:
        """An answer matching all fragments and gold facts should get 1.0."""
        from mind.fixtures.episode_answer_bench import AnswerKind, EpisodeAnswerBenchCase

        case = EpisodeAnswerBenchCase(
            case_id="test_perfect",
            task_id="task-001",
            episode_id="episode-001",
            prompt="What?",
            answer_kind=AnswerKind.SUMMARY,
            required_fragments=("success", "completed"),
            gold_fact_ids=("obj-1",),
            gold_memory_refs=("obj-1",),
            max_answer_tokens=20,
        )
        answer = GeneratedAnswer(text="success completed", support_ids=("obj-1",))
        score = score_answer(case, answer)

        assert score.task_completion_score == 1.0
        assert score.gold_fact_coverage == 1.0
        assert score.answer_faithfulness == 1.0
        assert score.task_success is True

    def test_score_answer_faithfulness_zero_when_no_overlap(self) -> None:
        """Support ids that don't overlap gold facts → faithfulness 0."""
        from mind.fixtures.episode_answer_bench import AnswerKind, EpisodeAnswerBenchCase

        case = EpisodeAnswerBenchCase(
            case_id="test_no_faith",
            task_id="task-001",
            episode_id="episode-001",
            prompt="What?",
            answer_kind=AnswerKind.SUMMARY,
            required_fragments=("hello",),
            gold_fact_ids=("gold-1",),
            gold_memory_refs=("gold-1",),
            max_answer_tokens=20,
        )
        answer = GeneratedAnswer(text="hello world", support_ids=("wrong-id",))
        score = score_answer(case, answer)

        assert score.answer_faithfulness == 0.0
        assert score.gold_fact_coverage == 0.0

    def test_answer_from_workspace_length_mismatch_raises(self) -> None:
        """If slots and selected_object_ids lengths differ, raise RuntimeError."""
        from mind.workspace.context_protocol import SerializedContext

        bad_payload = json.dumps({
            "protocol": "mind.phase_d_context.v1",
            "kind": "workspace",
            "task_id": "test",
            "selected_object_ids": ["obj-1", "obj-2"],
            "slots": [{"summary": "only one slot", "source_refs": ["obj-1"]}],
        })
        bad_context = SerializedContext(
            protocol="mind.phase_d_context.v1",
            kind="workspace",
            object_ids=("obj-1", "obj-2"),
            text=bad_payload,
            token_count=10,
        )
        from mind.fixtures.episode_answer_bench import AnswerKind, EpisodeAnswerBenchCase

        case = EpisodeAnswerBenchCase(
            case_id="test_mismatch",
            task_id="task-001",
            episode_id="episode-001",
            prompt="What?",
            answer_kind=AnswerKind.SUMMARY,
            required_fragments=("x",),
            gold_fact_ids=("obj-1",),
            gold_memory_refs=("obj-1",),
            max_answer_tokens=10,
        )
        with pytest.raises(RuntimeError, match="length mismatch"):
            answer_from_workspace(case, bad_context)


# ---------------------------------------------------------------------------
# Service-level integration: multi-mode retrieve with query_embedder
# ---------------------------------------------------------------------------


class TestServiceMultiModeRetrieval:
    """Integration tests for PrimitiveService.retrieve with combined modes."""

    def test_keyword_plus_vector_retrieve(self, tmp_path: Path) -> None:
        """KEYWORD+VECTOR combined should return results."""
        db_path = tmp_path / "svc_multi.sqlite3"
        showcase = build_core_object_showcase()
        episode = build_golden_episode_set()[0]
        with SQLiteMemoryStore(db_path) as store:
            store.insert_objects(showcase)
            store.insert_objects(episode.objects)
            service = PrimitiveService(
                store,
                clock=lambda: FIXED_TIMESTAMP,
                query_embedder=build_query_embedding,
            )
            result = service.retrieve(
                {
                    "query": "showcase summary",
                    "query_modes": ["keyword", "vector"],
                    "budget": {"max_cost": 10.0, "max_candidates": 5},
                    "filters": {"object_types": ["SummaryNote"]},
                },
                _context(),
            )
        assert result.outcome is PrimitiveOutcome.SUCCESS
        assert result.response is not None
        response = RetrieveResponse.model_validate(result.response)
        assert len(response.candidate_ids) > 0
        assert "showcase-summary" in response.candidate_ids

    def test_all_three_modes_retrieve(self, tmp_path: Path) -> None:
        """KEYWORD+TIME_WINDOW+VECTOR combined should return results."""
        db_path = tmp_path / "svc_triple.sqlite3"
        showcase = build_core_object_showcase()
        with SQLiteMemoryStore(db_path) as store:
            store.insert_objects(showcase)
            service = PrimitiveService(
                store,
                clock=lambda: FIXED_TIMESTAMP,
                query_embedder=build_query_embedding,
            )
            result = service.retrieve(
                {
                    "query": {
                        "start": "2026-01-01T00:00:00+00:00",
                        "end": "2026-01-01T00:02:00+00:00",
                    },
                    "query_modes": ["keyword", "time_window", "vector"],
                    "budget": {"max_cost": 10.0, "max_candidates": 10},
                    "filters": {},
                },
                _context(),
            )
        assert result.outcome is PrimitiveOutcome.SUCCESS
        assert result.response is not None
        response = RetrieveResponse.model_validate(result.response)
        assert len(response.candidate_ids) > 0

    def test_vector_only_with_embedder_succeeds(self, tmp_path: Path) -> None:
        """VECTOR-only mode with query_embedder (no vector_retriever) should pass."""
        db_path = tmp_path / "svc_vec.sqlite3"
        showcase = build_core_object_showcase()
        with SQLiteMemoryStore(db_path) as store:
            store.insert_objects(showcase)
            service = PrimitiveService(
                store,
                clock=lambda: FIXED_TIMESTAMP,
                query_embedder=build_query_embedding,
            )
            result = service.retrieve(
                {
                    "query": "vector:showcase-summary",
                    "query_modes": ["vector"],
                    "budget": {"max_cost": 10.0, "max_candidates": 5},
                    "filters": {"object_types": ["SummaryNote"]},
                },
                _context(),
            )
        assert result.outcome is PrimitiveOutcome.SUCCESS
        assert result.response is not None
        response = RetrieveResponse.model_validate(result.response)
        assert "showcase-summary" in response.candidate_ids
