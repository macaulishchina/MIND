"""Governance gate evaluation helpers."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from mind.kernel.provenance import HIGH_SENSITIVITY_PROVENANCE_FIELDS
from mind.kernel.replay import replay_episode
from mind.kernel.store import MemoryStoreFactory, SQLiteMemoryStore
from mind.offline import (
    OfflineJobKind,
    OfflineMaintenanceService,
    ReflectEpisodeJobPayload,
    new_offline_job,
    select_replay_targets,
)
from mind.primitives.contracts import (
    Capability,
    PrimitiveErrorCode,
    PrimitiveOutcome,
)
from mind.primitives.service import PrimitiveService
from mind.workspace import WorkspaceBuilder

from .gate_helpers import (
    assert_governance_gate,  # noqa: F401
)
from .gate_helpers import (
    governance_context as _context,
)
from .gate_helpers import (
    ranking_isolation_regression as _ranking_isolation_regression,
)
from .service import GovernanceService

_FIXED_TIMESTAMP = datetime(2026, 3, 10, 14, 0, tzinfo=UTC)


@dataclass(frozen=True)
class GovernanceGateResult:
    raw_object_count: int
    direct_provenance_count: int
    authoritative_binding_count: int
    duplicate_provenance_count: int
    orphan_provenance_count: int
    valid_bound_type_count: int
    low_privilege_block_count: int
    low_privilege_total: int
    low_privilege_clean_read_count: int
    privileged_summary_count: int
    privileged_total: int
    privileged_high_sensitivity_leak_count: int
    online_conceal_block_count: int
    online_conceal_total: int
    offline_conceal_block_count: int
    offline_conceal_total: int
    governance_audit_stage_sequence: tuple[str, ...]
    search_text_isolated: bool
    embedding_text_isolated: bool
    object_embedding_isolated: bool
    provenance_query_hit_count: int

    @property
    def h1_pass(self) -> bool:
        return (
            self.raw_object_count > 0 and self.authoritative_binding_count == self.raw_object_count
        )

    @property
    def h2_pass(self) -> bool:
        return (
            self.direct_provenance_count == self.raw_object_count
            and self.duplicate_provenance_count == 0
            and self.orphan_provenance_count == 0
            and self.valid_bound_type_count == self.direct_provenance_count
        )

    @property
    def h3_pass(self) -> bool:
        return (
            self.low_privilege_total > 0
            and self.low_privilege_block_count == self.low_privilege_total
            and self.low_privilege_clean_read_count == 1
        )

    @property
    def h4_pass(self) -> bool:
        return (
            self.privileged_total > 0
            and self.privileged_summary_count == self.privileged_total
            and self.privileged_high_sensitivity_leak_count == 0
        )

    @property
    def h5_pass(self) -> bool:
        return (
            self.online_conceal_total > 0
            and self.online_conceal_block_count == self.online_conceal_total
        )

    @property
    def h6_pass(self) -> bool:
        return (
            self.offline_conceal_total > 0
            and self.offline_conceal_block_count == self.offline_conceal_total
        )

    @property
    def h7_pass(self) -> bool:
        return self.governance_audit_stage_sequence == ("plan", "preview", "execute")

    @property
    def h8_pass(self) -> bool:
        return (
            self.search_text_isolated
            and self.embedding_text_isolated
            and self.object_embedding_isolated
            and self.provenance_query_hit_count == 0
        )

    @property
    def governance_gate_pass(self) -> bool:
        return (
            self.h1_pass
            and self.h2_pass
            and self.h3_pass
            and self.h4_pass
            and self.h5_pass
            and self.h6_pass
            and self.h7_pass
            and self.h8_pass
        )


def evaluate_governance_gate(
    db_path: str | Path | None = None,
    store_factory: MemoryStoreFactory | None = None,
) -> GovernanceGateResult:
    """Run the formal governance gate."""

    def default_store_factory(store_path: Path) -> SQLiteMemoryStore:
        return SQLiteMemoryStore(store_path)

    def run(store_path: Path, active_store_factory: MemoryStoreFactory) -> GovernanceGateResult:
        with active_store_factory(store_path) as store:
            primitive_service = PrimitiveService(store, clock=lambda: _FIXED_TIMESTAMP)
            governance_service = GovernanceService(store, clock=lambda: _FIXED_TIMESTAMP)
            workspace_builder = WorkspaceBuilder(store, clock=lambda: _FIXED_TIMESTAMP)
            maintenance_service = OfflineMaintenanceService(store, clock=lambda: _FIXED_TIMESTAMP)

            writer_context = _context(
                actor="phase-h-writer",
                capabilities=[Capability.MEMORY_READ],
            )
            raw_specs = (
                {
                    "record_kind": "user_message",
                    "content": {"text": "alpha hidden memory from user a"},
                    "episode_id": "phase-h-episode",
                    "timestamp_order": 1,
                    "direct_provenance": {
                        "producer_kind": "user",
                        "producer_id": "user-a",
                        "captured_at": "2026-03-09T09:00:00+00:00",
                        "source_channel": "chat",
                        "tenant_id": "tenant-phase-h",
                        "user_id": "user-a",
                        "ip_addr": "203.0.113.11",
                        "device_id": "device-hidden",
                        "machine_fingerprint": "fingerprint-hidden",
                        "session_id": "session-hidden",
                        "request_id": "request-hidden",
                        "conversation_id": "conversation-hidden",
                        "episode_id": "phase-h-episode",
                    },
                },
                {
                    "record_kind": "assistant_message",
                    "content": {"text": "beta visible memory from assistant"},
                    "episode_id": "phase-h-episode",
                    "timestamp_order": 2,
                    "direct_provenance": {
                        "producer_kind": "model",
                        "producer_id": "model-a",
                        "captured_at": "2026-03-09T09:01:00+00:00",
                        "source_channel": "chat",
                        "tenant_id": "tenant-phase-h",
                        "model_id": "model-a",
                        "model_provider": "openai",
                        "model_version": "2026-03",
                        "episode_id": "phase-h-episode",
                    },
                },
                {
                    "record_kind": "system_event",
                    "content": {"event": "cache-sync-complete"},
                    "episode_id": "phase-h-episode",
                    "timestamp_order": 3,
                    "direct_provenance": {
                        "producer_kind": "system",
                        "producer_id": "worker-a",
                        "captured_at": "2026-03-09T09:02:00+00:00",
                        "source_channel": "system_internal",
                        "tenant_id": "tenant-phase-h",
                        "episode_id": "phase-h-episode",
                    },
                },
            )

            write_results = [
                primitive_service.write_raw(spec, writer_context) for spec in raw_specs
            ]
            raw_ids: list[str] = []
            for result in write_results:
                if result.outcome is not PrimitiveOutcome.SUCCESS or result.response is None:
                    raise RuntimeError("governance gate setup failed: write_raw did not succeed")
                raw_ids.append(str(result.response["object_id"]))

            hidden_raw_id = raw_ids[0]
            visible_raw_ids = raw_ids[1:]
            store.insert_object(
                {
                    "id": "phase-h-episode",
                    "type": "TaskEpisode",
                    "content": {
                        "title": "governance gate episode",
                        "result_summary": "success",
                    },
                    "source_refs": list(raw_ids),
                    "created_at": _FIXED_TIMESTAMP.isoformat(),
                    "updated_at": _FIXED_TIMESTAMP.isoformat(),
                    "version": 1,
                    "status": "active",
                    "priority": 0.6,
                    "metadata": {
                        "task_id": "phase-h-task",
                        "goal": "validate provenance foundation semantics",
                        "result": "success",
                        "success": True,
                        "record_refs": list(raw_ids),
                    },
                }
            )

            low_privilege_context = _context(
                actor="phase-h-reader",
                capabilities=[Capability.MEMORY_READ],
            )
            privileged_read_context = _context(
                actor="phase-h-auditor",
                capabilities=[
                    Capability.MEMORY_READ,
                    Capability.MEMORY_READ_WITH_PROVENANCE,
                ],
            )
            governance_plan_context = _context(
                actor="phase-h-planner",
                capabilities=[Capability.GOVERNANCE_PLAN],
            )
            governance_execute_context = _context(
                actor="phase-h-executor",
                capabilities=[Capability.GOVERNANCE_EXECUTE],
            )

            low_privilege_read = primitive_service.read(
                {"object_ids": [hidden_raw_id], "include_provenance": True},
                low_privilege_context,
            )
            low_privilege_read_helper = primitive_service.read_with_provenance(
                {"object_ids": [hidden_raw_id]},
                low_privilege_context,
            )
            normal_read = primitive_service.read(
                {"object_ids": [hidden_raw_id]},
                low_privilege_context,
            )
            privileged_read = primitive_service.read_with_provenance(
                {"object_ids": [hidden_raw_id]},
                privileged_read_context,
            )

            plan = governance_service.plan_conceal(
                {
                    "selector": {"object_ids": [hidden_raw_id]},
                    "reason": "phase h gate conceal target",
                },
                governance_plan_context,
            )
            preview = governance_service.preview_conceal(
                {"operation_id": plan.operation_id},
                governance_plan_context,
            )
            governance_service.execute_conceal(
                {"operation_id": plan.operation_id},
                governance_execute_context,
            )

            concealed_read = primitive_service.read(
                {"object_ids": [hidden_raw_id]},
                low_privilege_context,
            )
            concealed_retrieve = primitive_service.retrieve(
                {
                    "query": "alpha hidden memory",
                    "query_modes": ["keyword"],
                    "budget": {"max_cost": 5.0, "max_candidates": 10},
                    "filters": {"object_types": ["RawRecord"]},
                },
                low_privilege_context,
            )
            workspace_result = workspace_builder.build(
                task_id="phase-h-task",
                candidate_ids=[hidden_raw_id, visible_raw_ids[0]],
                candidate_scores=[0.9, 0.4],
                slot_limit=2,
            )

            replayed_records = replay_episode(store, "phase-h-episode")
            reflect_result = maintenance_service.process_job(
                new_offline_job(
                    job_id="phase-h-offline-reflect",
                    job_kind=OfflineJobKind.REFLECT_EPISODE,
                    payload=ReflectEpisodeJobPayload(
                        episode_id="phase-h-episode",
                        focus="phase h offline conceal regression",
                    ),
                    now=_FIXED_TIMESTAMP,
                ),
                actor="phase-h-offline-worker",
            )
            replay_targets = select_replay_targets(store, tuple(raw_ids), top_k=len(raw_ids))

            provenance_rows = store.iter_direct_provenance()
            governance_rows = store.iter_governance_audit_for_operation(plan.operation_id)

        raw_like_types = {"RawRecord", "ImportedRawRecord"}
        raw_object_count = len(raw_ids)
        provenance_rows_by_object: dict[str, list[object]] = {}
        authoritative_binding_count = 0
        duplicate_provenance_count = 0
        orphan_provenance_count = 0
        valid_bound_type_count = 0
        for row in provenance_rows:
            provenance_rows_by_object.setdefault(row.bound_object_id, []).append(row)
            if row.bound_object_type in raw_like_types:
                valid_bound_type_count += 1
            if row.bound_object_id not in raw_ids:
                orphan_provenance_count += 1
        for object_id in raw_ids:
            bound_rows = provenance_rows_by_object.get(object_id, [])
            if len(bound_rows) == 1:
                authoritative_binding_count += 1
            if len(bound_rows) > 1:
                duplicate_provenance_count += len(bound_rows) - 1

        low_privilege_block_count = sum(
            result.outcome is PrimitiveOutcome.REJECTED
            and result.error is not None
            and result.error.code is PrimitiveErrorCode.CAPABILITY_REQUIRED
            for result in (low_privilege_read, low_privilege_read_helper)
        )
        low_privilege_clean_read_count = int(
            normal_read.outcome is PrimitiveOutcome.SUCCESS
            and normal_read.response is not None
            and normal_read.response["provenance_summaries"] == {}
        )

        privileged_high_sensitivity_leak_count = 0
        privileged_summary_count = 0
        if (
            privileged_read.outcome is PrimitiveOutcome.SUCCESS
            and privileged_read.response is not None
        ):
            summary = privileged_read.response["provenance_summaries"].get(hidden_raw_id)
            if isinstance(summary, dict):
                privileged_summary_count += 1
                if HIGH_SENSITIVITY_PROVENANCE_FIELDS.intersection(summary):
                    privileged_high_sensitivity_leak_count += 1
        preview_summary = preview.provenance_summaries.get(hidden_raw_id)
        if preview_summary is not None:
            privileged_summary_count += 1
            preview_payload = preview_summary.model_dump(mode="json")
            if HIGH_SENSITIVITY_PROVENANCE_FIELDS.intersection(preview_payload):
                privileged_high_sensitivity_leak_count += 1

        online_conceal_block_count = 0
        if (
            concealed_read.outcome is PrimitiveOutcome.REJECTED
            and concealed_read.error is not None
            and concealed_read.error.code is PrimitiveErrorCode.OBJECT_INACCESSIBLE
        ):
            online_conceal_block_count += 1
        if (
            concealed_retrieve.outcome is PrimitiveOutcome.SUCCESS
            and concealed_retrieve.response is not None
            and hidden_raw_id not in concealed_retrieve.response["candidate_ids"]
        ):
            online_conceal_block_count += 1
        if (
            hidden_raw_id not in workspace_result.selected_ids
            and hidden_raw_id in workspace_result.skipped_ids
        ):
            online_conceal_block_count += 1

        offline_conceal_block_count = 0
        if hidden_raw_id not in [record["id"] for record in replayed_records]:
            offline_conceal_block_count += 1
        if hidden_raw_id not in reflect_result["source_refs"]:
            offline_conceal_block_count += 1
        if hidden_raw_id not in [target.object_id for target in replay_targets]:
            offline_conceal_block_count += 1

        governance_audit_stage_sequence = tuple(row.stage.value for row in governance_rows)
        (
            search_text_isolated,
            embedding_text_isolated,
            object_embedding_isolated,
            provenance_query_hit_count,
        ) = _ranking_isolation_regression()

        return GovernanceGateResult(
            raw_object_count=raw_object_count,
            direct_provenance_count=len(provenance_rows),
            authoritative_binding_count=authoritative_binding_count,
            duplicate_provenance_count=duplicate_provenance_count,
            orphan_provenance_count=orphan_provenance_count,
            valid_bound_type_count=valid_bound_type_count,
            low_privilege_block_count=low_privilege_block_count,
            low_privilege_total=2,
            low_privilege_clean_read_count=low_privilege_clean_read_count,
            privileged_summary_count=privileged_summary_count,
            privileged_total=2,
            privileged_high_sensitivity_leak_count=privileged_high_sensitivity_leak_count,
            online_conceal_block_count=online_conceal_block_count,
            online_conceal_total=3,
            offline_conceal_block_count=offline_conceal_block_count,
            offline_conceal_total=3,
            governance_audit_stage_sequence=governance_audit_stage_sequence,
            search_text_isolated=search_text_isolated,
            embedding_text_isolated=embedding_text_isolated,
            object_embedding_isolated=object_embedding_isolated,
            provenance_query_hit_count=provenance_query_hit_count,
        )

    active_factory = store_factory or default_store_factory
    if db_path is not None:
        return run(Path(db_path), active_factory)

    with tempfile.TemporaryDirectory() as tmpdir:
        return run(Path(tmpdir) / "governance_gate.sqlite3", active_factory)
