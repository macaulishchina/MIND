"""Phase β gate tests: dense retrieval, conflict detection, workspace diversity,
promotion lifecycle, auto mode enhancement, evidence summary.

This file mirrors the structure of ``test_phase_alpha_gate.py`` and serves as
the formal acceptance gate for Phase β.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from mind.access.contracts import (
    AccessContextKind,
    AccessMode,
    AccessModeTraceEvent,
    AccessReasonCode,
    AccessRunResponse,
    AccessRunTrace,
    AccessSwitchKind,
    AccessTaskFamily,
    AccessTraceKind,
    EvidenceSummaryItem,
)
from mind.access.mode_history import ModeHistoryCache
from mind.kernel.embedding import (
    EmbeddingProvider,
    LocalHashEmbedding,
    embed_objects,
)
from mind.kernel.retrieval import EMBEDDING_DIM, matches_retrieval_filters
from mind.kernel.schema import VALID_PROPOSAL_STATUS, validate_object
from mind.kernel.store import SQLiteMemoryStore
from mind.offline import (
    OfflineJob,
    OfflineJobKind,
    OfflineJobStatus,
    new_offline_job,
)
from mind.offline.scheduler import OfflineJobScheduler
from mind.offline.service import OfflineMaintenanceService
from mind.offline_jobs import (
    RefreshEmbeddingsJobPayload,
    ResolveConflictJobPayload,
    VerifyProposalJobPayload,
)
from mind.primitives.conflict import (
    ConflictDetectionResult,
    ConflictRelation,
    detect_conflicts,
)
from mind.workspace.policy import (
    FLASH_POLICY,
    RECALL_POLICY,
    SlotAllocationPolicy,
    apply_diversity_policy,
    evidence_diversity_score,
)

FIXED_TIMESTAMP = datetime(2026, 3, 13, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts() -> str:
    return FIXED_TIMESTAMP.isoformat()


def _raw_object(
    object_id: str = "raw-001",
    episode_id: str = "ep-001",
    *,
    text: str = "content",
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "record_kind": "user_message",
        "episode_id": episode_id,
        "timestamp_order": 1,
    }
    if extra_meta:
        meta.update(extra_meta)
    return {
        "id": object_id,
        "type": "RawRecord",
        "content": {"text": text},
        "source_refs": [],
        "created_at": _ts(),
        "updated_at": _ts(),
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": meta,
    }


def _schema_note(
    object_id: str = "schema-001",
    *,
    proposal_status: str | None = None,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    refs = evidence_refs or ["ref-001", "ref-002"]
    meta: dict[str, Any] = {
        "kind": "semantic",
        "evidence_refs": refs,
        "stability_score": 0.75,
        "promotion_source_refs": refs,
    }
    if proposal_status is not None:
        meta["proposal_status"] = proposal_status
    return {
        "id": object_id,
        "type": "SchemaNote",
        "content": {"rule": "test rule"},
        "source_refs": refs,
        "created_at": _ts(),
        "updated_at": _ts(),
        "version": 1,
        "status": "active",
        "priority": 0.65,
        "metadata": meta,
    }


def _obj_pair(
    object_id: str,
    *,
    object_type: str = "RawRecord",
    episode_id: str = "ep-001",
    score: float = 0.5,
    conflict_candidates: list | None = None,
) -> tuple[dict[str, Any], float]:
    meta: dict[str, Any] = {
        "record_kind": "user_message",
        "episode_id": episode_id,
        "timestamp_order": 1,
    }
    if conflict_candidates is not None:
        meta["conflict_candidates"] = conflict_candidates
    if object_type != "RawRecord":
        meta.pop("record_kind", None)
        meta.pop("timestamp_order", None)
    return {
        "id": object_id,
        "type": object_type,
        "content": {"text": f"content for {object_id}"},
        "source_refs": [f"src-{object_id}"],
        "created_at": _ts(),
        "updated_at": _ts(),
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": meta,
    }, score


def _flash_trace(mode: AccessMode = AccessMode.FLASH) -> AccessRunTrace:
    return AccessRunTrace(
        requested_mode=mode,
        resolved_mode=AccessMode.FLASH,
        events=[
            AccessModeTraceEvent(
                event_kind=AccessTraceKind.SELECT_MODE,
                mode=AccessMode.FLASH,
                summary="flash selected",
                reason_code=AccessReasonCode.EXPLICIT_MODE_REQUEST,
                switch_kind=AccessSwitchKind.INITIAL,
            ),
            AccessModeTraceEvent(
                event_kind=AccessTraceKind.MODE_SUMMARY,
                mode=AccessMode.FLASH,
                summary="flash complete",
            ),
        ],
    )


class _FakeJobStore:
    def __init__(self) -> None:
        self._jobs: list[OfflineJob] = []

    def enqueue_offline_job(self, job: OfflineJob | dict[str, Any]) -> None:
        self._jobs.append(OfflineJob.model_validate(job))

    def iter_offline_jobs(self, *, statuses: Iterable[OfflineJobStatus] = ()) -> list[OfflineJob]:
        return list(self._jobs)

    def claim_offline_job(
        self, *, worker_id: str, now: Any, job_kinds: Any = (),
    ) -> OfflineJob | None:
        return None

    def complete_offline_job(
        self, job_id: str, *, worker_id: str, completed_at: Any, result: Any,
    ) -> None:
        pass

    def fail_offline_job(
        self, job_id: str, *, worker_id: str, failed_at: Any, error: Any,
    ) -> None:
        pass

    def cancel_offline_job(
        self,
        job_id: str,
        *,
        cancelled_at: Any = None,
        error: Any = None,
    ) -> None:
        pass


# ===========================================================================
# β-1: Dense Retrieval / Embedding Provider
# ===========================================================================


def test_β1_local_hash_embedding_satisfies_protocol() -> None:
    """β-1: LocalHashEmbedding satisfies EmbeddingProvider protocol."""
    provider = LocalHashEmbedding()
    assert isinstance(provider, EmbeddingProvider)
    assert provider.dimension == EMBEDDING_DIM


def test_β1_local_hash_embedding_is_deterministic() -> None:
    """β-1: Same text always produces same vector."""
    p = LocalHashEmbedding()
    v1 = p.embed(["hello world"])[0]
    v2 = p.embed(["hello world"])[0]
    assert v1 == v2


def test_β1_embed_objects_returns_mapping() -> None:
    """β-1: embed_objects returns id → vector mapping."""
    objs = [_raw_object("a"), _raw_object("b", "ep-002")]
    result = embed_objects(objs)
    assert set(result.keys()) == {"a", "b"}
    for vec in result.values():
        assert len(vec) == EMBEDDING_DIM


def test_β1_refresh_embeddings_job_kind_exists() -> None:
    """β-1: REFRESH_EMBEDDINGS is a valid OfflineJobKind."""
    assert OfflineJobKind.REFRESH_EMBEDDINGS == "refresh_embeddings"


def test_β1_refresh_embeddings_job_payload_validates() -> None:
    """β-1: RefreshEmbeddingsJobPayload validates successfully."""
    payload = RefreshEmbeddingsJobPayload(object_ids=["obj-001"], reason="test")
    assert payload.object_ids == ["obj-001"]


def test_β1_scheduler_schedule_refresh_embeddings_enqueues_job() -> None:
    """β-1: OfflineJobScheduler.schedule_refresh_embeddings enqueues REFRESH_EMBEDDINGS."""
    job_store = _FakeJobStore()
    scheduler = OfflineJobScheduler(job_store, clock=lambda: FIXED_TIMESTAMP)
    job_id = scheduler.schedule_refresh_embeddings(["obj-001"])
    assert job_id is not None
    jobs = job_store.iter_offline_jobs()
    assert len(jobs) == 1
    assert jobs[0].job_kind is OfflineJobKind.REFRESH_EMBEDDINGS


def test_β1_offline_service_handles_refresh_embeddings(tmp_path: Path) -> None:
    """β-1: OfflineMaintenanceService processes REFRESH_EMBEDDINGS jobs."""
    with SQLiteMemoryStore(tmp_path / "β1.sqlite3") as store:
        obj = _raw_object("obj-001")
        store.insert_object(obj)
        service = OfflineMaintenanceService(store)
        job = new_offline_job(
            job_kind=OfflineJobKind.REFRESH_EMBEDDINGS,
            payload=RefreshEmbeddingsJobPayload(object_ids=["obj-001"]),
            now=FIXED_TIMESTAMP,
        )
        result = service.process_job(job, actor="test-actor")
    assert result["job_kind"] == "refresh_embeddings"
    assert isinstance(result["refreshed_count"], int)


# ===========================================================================
# β-2: Input Conflict Detection
# ===========================================================================


def test_β2_conflict_relation_enum_complete() -> None:
    """β-2: ConflictRelation enum has all 5 expected values."""
    expected = {"duplicate", "refine", "contradict", "supersede", "novel"}
    assert {r.value for r in ConflictRelation} == expected


def test_β2_conflict_detection_result_immutable() -> None:
    """β-2: ConflictDetectionResult is a frozen dataclass."""
    r = ConflictDetectionResult(
        relation=ConflictRelation.NOVEL,
        confidence=0.5,
        neighbor_id="n-001",
        explanation="test",
    )
    with pytest.raises((AttributeError, TypeError)):
        r.confidence = 0.9  # type: ignore[misc]


def test_β2_detect_conflicts_no_neighbors(tmp_path: Path) -> None:
    """β-2: detect_conflicts returns [] when store has no other objects."""
    with SQLiteMemoryStore(tmp_path / "β2.sqlite3") as store:
        obj = _raw_object("new-001")
        store.insert_object(obj)
        results = detect_conflicts(store, obj)
    assert results == []


def test_β2_detect_conflicts_returns_valid_results(tmp_path: Path) -> None:
    """β-2: detect_conflicts returns ConflictDetectionResult objects."""
    with SQLiteMemoryStore(tmp_path / "β2b.sqlite3") as store:
        store.insert_object(_raw_object("old-001", text="memory for AI"))
        new_obj = _raw_object("new-001", text="memory for AI models")
        store.insert_object(new_obj)
        results = detect_conflicts(store, new_obj)
    for r in results:
        assert isinstance(r, ConflictDetectionResult)
        assert r.relation in ConflictRelation


def test_β2_resolve_conflict_job_kind_exists() -> None:
    """β-2: RESOLVE_CONFLICT is a valid OfflineJobKind."""
    assert OfflineJobKind.RESOLVE_CONFLICT == "resolve_conflict"


def test_β2_scheduler_enqueues_resolve_conflict_on_contradiction() -> None:
    """β-2: OfflineJobScheduler enqueues RESOLVE_CONFLICT when contradiction found."""
    job_store = _FakeJobStore()
    scheduler = OfflineJobScheduler(job_store, clock=lambda: FIXED_TIMESTAMP)
    candidates = [
        {"relation": "contradict", "confidence": 0.9, "neighbor_id": "old", "explanation": "test"}
    ]
    job_id = scheduler.on_conflict_detected("new-001", candidates)
    assert job_id is not None
    assert job_store.iter_offline_jobs()[0].job_kind is OfflineJobKind.RESOLVE_CONFLICT


def test_β2_scheduler_skips_resolve_conflict_without_contradiction() -> None:
    """β-2: OfflineJobScheduler does not enqueue RESOLVE_CONFLICT for non-contradictions."""
    job_store = _FakeJobStore()
    scheduler = OfflineJobScheduler(job_store, clock=lambda: FIXED_TIMESTAMP)
    candidates = [
        {"relation": "novel", "confidence": 0.9, "neighbor_id": "old", "explanation": "test"}
    ]
    job_id = scheduler.on_conflict_detected("new-001", candidates)
    assert job_id is None


def test_β2_offline_service_handles_resolve_conflict(tmp_path: Path) -> None:
    """β-2: OfflineMaintenanceService processes RESOLVE_CONFLICT jobs."""
    with SQLiteMemoryStore(tmp_path / "β2c.sqlite3") as store:
        obj = _raw_object("obj-001")
        store.insert_object(obj)
        service = OfflineMaintenanceService(store)
        job = new_offline_job(
            job_kind=OfflineJobKind.RESOLVE_CONFLICT,
            payload=ResolveConflictJobPayload(
                object_id="new-001",
                conflict_candidates=[
                    {
                        "relation": "contradict",
                        "confidence": 0.95,
                        "neighbor_id": "obj-001",
                        "explanation": "direct contradiction",
                    }
                ],
            ),
            now=FIXED_TIMESTAMP,
        )
        result = service.process_job(job, actor="test-actor")
    assert result["job_kind"] == "resolve_conflict"
    assert result["object_id"] == "new-001"


# ===========================================================================
# β-3: Workspace Evidence Diversity
# ===========================================================================


def test_β3_slot_allocation_policy_defaults() -> None:
    """β-3: SlotAllocationPolicy default constraints are correct."""
    p = SlotAllocationPolicy()
    assert p.min_raw_evidence_slots == 1
    assert p.min_diverse_episode_slots == 1
    assert p.include_conflict_evidence is True


def test_β3_flash_policy_has_no_diversity() -> None:
    """β-3: FLASH_POLICY requires no diversity."""
    assert FLASH_POLICY.min_raw_evidence_slots == 0
    assert FLASH_POLICY.min_diverse_episode_slots == 0


def test_β3_apply_diversity_policy_respects_slot_limit() -> None:
    """β-3: apply_diversity_policy never returns more than slot_limit items."""
    candidates = [_obj_pair(f"o{i}", episode_id="ep-001", score=float(i)) for i in range(8)]
    candidates.sort(key=lambda x: x[1], reverse=True)
    selected = apply_diversity_policy(candidates, slot_limit=3, policy=RECALL_POLICY)
    assert len(selected) <= 3


def test_β3_apply_diversity_policy_promotes_diverse_episodes() -> None:
    """β-3: Diversity rebalancing includes objects from different episodes."""
    # 4 high-score objects from ep-001, 1 low-score from ep-002
    candidates = [_obj_pair(f"a{i}", episode_id="ep-001", score=float(10 - i)) for i in range(4)]
    candidates.append(_obj_pair("b0", episode_id="ep-002", score=0.1))
    candidates.sort(key=lambda x: x[1], reverse=True)
    selected = apply_diversity_policy(candidates, slot_limit=4, policy=RECALL_POLICY)
    episodes = {obj["metadata"]["episode_id"] for obj, _ in selected}
    assert "ep-002" in episodes


def test_β3_evidence_diversity_score_in_range() -> None:
    """β-3: evidence_diversity_score returns a value in [0, 1]."""
    objs = [_obj_pair(f"o{i}", episode_id=f"ep-{i}")[0] for i in range(4)]
    score = evidence_diversity_score(objs)
    assert 0.0 <= score <= 1.0


def test_β3_evidence_diversity_score_higher_with_multi_episode() -> None:
    """β-3: Multi-episode selection has higher diversity score than single-episode."""
    single = [_obj_pair(f"o{i}", episode_id="ep-001")[0] for i in range(4)]
    multi = [_obj_pair(f"p{i}", episode_id=f"ep-{i}")[0] for i in range(4)]
    assert evidence_diversity_score(multi) >= evidence_diversity_score(single)


# ===========================================================================
# β-4: Promotion Pipeline + Proposal Lifecycle
# ===========================================================================


def test_β4_valid_proposal_status_set() -> None:
    """β-4: VALID_PROPOSAL_STATUS contains exactly the expected values."""
    assert VALID_PROPOSAL_STATUS == {"proposed", "verified", "committed", "rejected"}


def test_β4_schema_note_proposed_validates() -> None:
    """β-4: SchemaNote with proposal_status=proposed passes schema validation."""
    errors = validate_object(_schema_note(proposal_status="proposed"))
    assert errors == []


def test_β4_schema_note_invalid_proposal_status_fails_validation() -> None:
    """β-4: SchemaNote with unknown proposal_status fails validation."""
    errors = validate_object(_schema_note(proposal_status="unknown_state"))
    assert any("proposal_status" in e for e in errors)


def test_β4_proposed_schema_excluded_from_retrieval() -> None:
    """β-4: Proposed SchemaNote is excluded from default retrieval."""
    obj = _schema_note(proposal_status="proposed")
    assert not matches_retrieval_filters(
        obj, object_types=[], statuses=[], episode_id=None, task_id=None
    )


def test_β4_rejected_schema_excluded_from_retrieval() -> None:
    """β-4: Rejected SchemaNote is excluded from default retrieval."""
    obj = _schema_note(proposal_status="rejected")
    assert not matches_retrieval_filters(
        obj, object_types=[], statuses=[], episode_id=None, task_id=None
    )


def test_β4_committed_schema_included_in_retrieval() -> None:
    """β-4: Committed SchemaNote participates in default retrieval."""
    obj = _schema_note(proposal_status="committed")
    assert matches_retrieval_filters(
        obj, object_types=[], statuses=[], episode_id=None, task_id=None
    )


def test_β4_schema_without_proposal_status_included_in_retrieval() -> None:
    """β-4: SchemaNote without proposal_status is backward-compat committed."""
    obj = _schema_note()
    assert matches_retrieval_filters(
        obj, object_types=[], statuses=[], episode_id=None, task_id=None
    )


def test_β4_verify_proposal_job_kind_exists() -> None:
    """β-4: VERIFY_PROPOSAL is a valid OfflineJobKind."""
    assert OfflineJobKind.VERIFY_PROPOSAL == "verify_proposal"


def test_β4_scheduler_enqueues_verify_proposal() -> None:
    """β-4: OfflineJobScheduler.on_schema_promoted enqueues VERIFY_PROPOSAL."""
    job_store = _FakeJobStore()
    scheduler = OfflineJobScheduler(job_store, clock=lambda: FIXED_TIMESTAMP)
    job_id = scheduler.on_schema_promoted("schema-001")
    assert job_id is not None
    jobs = job_store.iter_offline_jobs()
    assert len(jobs) == 1
    assert jobs[0].job_kind is OfflineJobKind.VERIFY_PROPOSAL
    assert jobs[0].payload["schema_note_id"] == "schema-001"


def test_β4_verify_proposal_commits_cross_episode(tmp_path: Path) -> None:
    """β-4: VERIFY_PROPOSAL promotes cross-episode SchemaNote to committed."""
    with SQLiteMemoryStore(tmp_path / "β4.sqlite3") as store:
        store.insert_object(_raw_object("r1", "ep-001"))
        store.insert_object(_raw_object("r2", "ep-002"))
        store.insert_object(
            _schema_note("s1", proposal_status="proposed", evidence_refs=["r1", "r2"])
        )
        service = OfflineMaintenanceService(store)
        job = new_offline_job(
            job_kind=OfflineJobKind.VERIFY_PROPOSAL,
            payload=VerifyProposalJobPayload(schema_note_id="s1"),
            now=FIXED_TIMESTAMP,
        )
        result = service.process_job(job, actor="test-actor")
        assert result["proposal_status"] == "committed"
        assert store.read_object("s1")["metadata"]["proposal_status"] == "committed"


def test_β4_verify_proposal_rejects_single_episode(tmp_path: Path) -> None:
    """β-4: VERIFY_PROPOSAL rejects a SchemaNote with only single-episode evidence."""
    with SQLiteMemoryStore(tmp_path / "β4b.sqlite3") as store:
        store.insert_object(_raw_object("r1", "ep-001"))
        store.insert_object(_raw_object("r2", "ep-001"))
        store.insert_object(
            _schema_note("s2", proposal_status="proposed", evidence_refs=["r1", "r2"])
        )
        service = OfflineMaintenanceService(store)
        job = new_offline_job(
            job_kind=OfflineJobKind.VERIFY_PROPOSAL,
            payload=VerifyProposalJobPayload(schema_note_id="s2"),
            now=FIXED_TIMESTAMP,
        )
        result = service.process_job(job, actor="test-actor")
        assert result["proposal_status"] == "rejected"
        assert store.read_object("s2")["metadata"]["proposal_status"] == "rejected"


# ===========================================================================
# β-5: Auto Mode Enhancement — ModeHistoryCache
# ===========================================================================


def test_β5_mode_history_cache_starts_empty() -> None:
    """β-5: ModeHistoryCache starts with no history."""
    assert ModeHistoryCache().preferred_mode() is None


def test_β5_mode_history_records_and_retrieves() -> None:
    """β-5: Recorded preferences influence preferred_mode."""
    cache = ModeHistoryCache()
    cache.record(AccessMode.RECALL, 1.0)
    cache.record(AccessMode.FLASH, -0.5)
    assert cache.preferred_mode() is AccessMode.RECALL


def test_β5_mode_history_task_family_scoped() -> None:
    """β-5: Preferences are tracked per task_family."""
    cache = ModeHistoryCache()
    cache.record(AccessMode.FLASH, 1.0, task_family=AccessTaskFamily.SPEED_SENSITIVE)
    cache.record(AccessMode.RECALL, 1.0, task_family=AccessTaskFamily.BALANCED)
    assert cache.preferred_mode(AccessTaskFamily.SPEED_SENSITIVE) is AccessMode.FLASH
    assert cache.preferred_mode(AccessTaskFamily.BALANCED) is AccessMode.RECALL


def test_β5_mode_history_build_from_feedback() -> None:
    """β-5: build_from_feedback_records correctly populates the cache."""
    feedbacks = [
        {
            "type": "FeedbackRecord",
            "metadata": {"access_mode": "recall", "quality_signal": 1.0},
        },
        {
            "type": "FeedbackRecord",
            "metadata": {"access_mode": "flash", "quality_signal": -0.5},
        },
    ]
    cache = ModeHistoryCache.build_from_feedback_records(feedbacks)
    assert cache.preferred_mode() is AccessMode.RECALL


def test_β5_mode_history_reset_clears_state() -> None:
    """β-5: reset() clears all accumulated history."""
    cache = ModeHistoryCache()
    cache.record(AccessMode.RECALL, 1.0)
    cache.reset()
    assert cache.preferred_mode() is None


# ===========================================================================
# β-S1: Evidence Summary
# ===========================================================================


def test_βS1_evidence_summary_item_validates() -> None:
    """β-S1: EvidenceSummaryItem validates with correct field values."""
    item = EvidenceSummaryItem(
        object_id="obj-001",
        object_type="RawRecord",
        brief="User mentioned project deadline",
        relevance_score=0.95,
    )
    assert item.object_id == "obj-001"
    assert 0.0 <= item.relevance_score <= 1.0


def test_βS1_access_run_response_has_evidence_summary_field() -> None:
    """β-S1: AccessRunResponse accepts evidence_summary field."""
    trace = _flash_trace()
    response = AccessRunResponse(
        resolved_mode=AccessMode.FLASH,
        context_kind=AccessContextKind.RAW_TOPK,
        context_text="context",
        context_token_count=5,
        trace=trace,
        evidence_summary=[
            EvidenceSummaryItem(
                object_id="obj-001",
                object_type="RawRecord",
                brief="brief text",
                relevance_score=0.8,
            )
        ],
    )
    assert len(response.evidence_summary) == 1
    assert response.evidence_summary[0].object_id == "obj-001"


def test_βS1_evidence_summary_defaults_to_empty() -> None:
    """β-S1: evidence_summary defaults to empty list (backward compat)."""
    trace = _flash_trace()
    response = AccessRunResponse(
        resolved_mode=AccessMode.FLASH,
        context_kind=AccessContextKind.RAW_TOPK,
        context_text="context",
        context_token_count=5,
        trace=trace,
    )
    assert response.evidence_summary == []


# ===========================================================================
# β gate pass condition
# ===========================================================================


def test_β_gate_all_job_kinds_registered() -> None:
    """β gate: All Phase β job kinds are registered in OfflineJobKind."""
    required = {
        OfflineJobKind.REFRESH_EMBEDDINGS,
        OfflineJobKind.RESOLVE_CONFLICT,
        OfflineJobKind.VERIFY_PROPOSAL,
    }
    assert required.issubset(set(OfflineJobKind))


def test_β_gate_new_scheduler_hooks_exist() -> None:
    """β gate: OfflineJobScheduler has all Phase β hooks."""
    scheduler = OfflineJobScheduler(_FakeJobStore(), clock=lambda: FIXED_TIMESTAMP)
    assert hasattr(scheduler, "on_conflict_detected")
    assert hasattr(scheduler, "on_schema_promoted")
    assert hasattr(scheduler, "schedule_refresh_embeddings")


def test_β_gate_evidence_summary_on_access_contract() -> None:
    """β gate: EvidenceSummaryItem and evidence_summary are on the access contracts."""
    # Check that EvidenceSummaryItem is importable from access.contracts
    from mind.access.contracts import AccessRunResponse, EvidenceSummaryItem  # noqa: F401

    fields = AccessRunResponse.model_fields
    assert "evidence_summary" in fields


def test_β_gate_embedding_provider_protocol_importable() -> None:
    """β gate: EmbeddingProvider protocol is importable from mind.kernel.embedding."""
    from mind.kernel.embedding import EmbeddingProvider, LocalHashEmbedding  # noqa: F401

    # Use isinstance to check protocol compliance (issubclass not supported for
    # protocols with non-method members like 'dimension').
    provider = LocalHashEmbedding()
    assert isinstance(provider, EmbeddingProvider)


def test_β_gate_conflict_module_importable() -> None:
    """β gate: mind.primitives.conflict exports all required symbols."""
    from mind.primitives.conflict import (  # noqa: F401
        ConflictDetectionResult,
        ConflictRelation,
        detect_conflicts,
    )


def test_β_gate_workspace_policy_importable() -> None:
    """β gate: mind.workspace.policy exports all required symbols."""
    from mind.workspace.policy import (  # noqa: F401
        SlotAllocationPolicy,
        apply_diversity_policy,
        evidence_diversity_score,
    )


def test_β_gate_mode_history_cache_importable() -> None:
    """β gate: mind.access.mode_history exports ModeHistoryCache."""
    from mind.access.mode_history import ModeHistoryCache  # noqa: F401
