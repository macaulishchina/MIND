"""Optional PostgreSQL integration coverage for Phase B/C/D/E gates."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from mind.fixtures.golden_episode_set import build_core_object_showcase, build_golden_episode_set
from mind.kernel.governance import (
    ConcealmentRecord,
    GovernanceAction,
    GovernanceAuditRecord,
    GovernanceCapability,
    GovernanceOutcome,
    GovernanceStage,
)
from mind.kernel.phase_b import evaluate_phase_b_gate
from mind.kernel.postgres_store import (
    PostgresMemoryStore,
    build_postgres_store_factory,
    run_postgres_migrations,
    temporary_postgres_database,
)
from mind.kernel.replay import replay_episode
from mind.kernel.retrieval import build_query_embedding
from mind.kernel.sql_tables import object_embeddings_table, object_versions_table
from mind.offline import (
    OfflineJobKind,
    OfflineJobStatus,
    ReflectEpisodeJobPayload,
    evaluate_phase_e_gate,
    new_offline_job,
)
from mind.primitives.contracts import PrimitiveExecutionContext, PrimitiveOutcome, RetrieveQueryMode
from mind.primitives.phase_c import evaluate_phase_c_gate
from mind.primitives.service import PrimitiveService
from mind.workspace import WorkspaceBuilder, evaluate_phase_d_smoke

POSTGRES_DSN = os.environ.get("MIND_TEST_POSTGRES_DSN")
FIXED_TIMESTAMP = datetime(2026, 3, 9, 19, 0, tzinfo=UTC)

pytestmark = pytest.mark.skipif(
    POSTGRES_DSN is None,
    reason="set MIND_TEST_POSTGRES_DSN to run PostgreSQL integration tests",
)


def test_postgres_memory_store_round_trip_and_gates() -> None:
    assert POSTGRES_DSN is not None

    with temporary_postgres_database(POSTGRES_DSN, prefix="mind_pytest_b") as database_dsn:
        run_postgres_migrations(database_dsn)
        with PostgresMemoryStore(database_dsn) as store:
            assert store.iter_objects() == []
            assert store.iter_primitive_call_logs() == []
            assert store.iter_budget_events() == []

        store_factory = build_postgres_store_factory(database_dsn)
        phase_b_result = evaluate_phase_b_gate(Path("phase_b.pg"), store_factory=store_factory)

    with temporary_postgres_database(POSTGRES_DSN, prefix="mind_pytest_c") as database_dsn:
        run_postgres_migrations(database_dsn)
        store_factory = build_postgres_store_factory(database_dsn)
        phase_c_result = evaluate_phase_c_gate(Path("phase_c.pg"), store_factory=store_factory)

    assert phase_b_result.phase_b_pass
    assert phase_c_result.phase_c_pass


def test_postgres_iter_latest_objects_applies_filters_and_latest_version() -> None:
    assert POSTGRES_DSN is not None

    showcase = build_core_object_showcase()
    episode = build_golden_episode_set()[3]
    invalid_task_episode: dict[str, Any] = {
        "id": "invalid-showcase-episode",
        "type": "TaskEpisode",
        "content": {"title": "invalid showcase episode"},
        "source_refs": [showcase[0]["id"]],
        "created_at": "2026-03-09T15:00:00+00:00",
        "updated_at": "2026-03-09T15:00:00+00:00",
        "version": 1,
        "status": "invalid",
        "priority": 0.8,
        "metadata": {
            "task_id": "showcase-task",
            "goal": "invalid task should not be retrieved by default",
            "result": "failure",
            "success": False,
            "record_refs": [showcase[0]["id"]],
        },
    }

    with temporary_postgres_database(POSTGRES_DSN, prefix="mind_retrieve") as database_dsn:
        run_postgres_migrations(database_dsn)
        with PostgresMemoryStore(database_dsn) as store:
            store.insert_objects(showcase)
            store.insert_objects(episode.objects)
            store.insert_object(invalid_task_episode)

            task_objects = store.iter_latest_objects(
                object_types=["TaskEpisode"],
                task_id="showcase-task",
            )
            summary_objects = store.iter_latest_objects(object_types=["SummaryNote"])

    assert [obj["id"] for obj in task_objects] == ["showcase-episode"]
    latest_summary = [
        obj for obj in summary_objects if obj["id"] == f"{episode.episode_id}-summary"
    ]
    assert len(latest_summary) == 1
    assert latest_summary[0]["version"] == 2


def test_postgres_workspace_builder_creates_valid_workspace() -> None:
    assert POSTGRES_DSN is not None

    showcase = build_core_object_showcase()
    episode = build_golden_episode_set()[0]

    with temporary_postgres_database(POSTGRES_DSN, prefix="mind_workspace") as database_dsn:
        run_postgres_migrations(database_dsn)
        with PostgresMemoryStore(database_dsn) as store:
            store.insert_objects(showcase)
            store.insert_objects(episode.objects)
            builder = WorkspaceBuilder(store)
            result = builder.build(
                task_id=episode.task_id,
                candidate_ids=[showcase[2]["id"], showcase[3]["id"], episode.episode_id],
                candidate_scores=[0.8, 0.7, 0.6],
                slot_limit=2,
            )

    assert result.workspace["type"] == "WorkspaceView"
    assert len(result.workspace["metadata"]["slots"]) == 2


def test_postgres_vector_search_persists_embeddings() -> None:
    assert POSTGRES_DSN is not None

    showcase = build_core_object_showcase()
    episode = build_golden_episode_set()[9]
    target_summary_id = f"{episode.episode_id}-summary"

    with temporary_postgres_database(POSTGRES_DSN, prefix="mind_vector") as database_dsn:
        run_postgres_migrations(database_dsn)
        with PostgresMemoryStore(database_dsn) as store:
            store.insert_objects(showcase)
            store.insert_objects(episode.objects)
            matches = store.search_latest_objects(
                query=f"vector:{target_summary_id}",
                query_modes=[RetrieveQueryMode.VECTOR],
                max_candidates=5,
                object_types=["SummaryNote"],
                query_embedding=build_query_embedding(f"vector:{target_summary_id}"),
            )
            with store.engine.connect() as connection:
                embedding_count = connection.execute(
                    sa.select(sa.func.count()).select_from(object_embeddings_table)
                ).scalar_one()
                search_text = connection.execute(
                    sa.select(object_versions_table.c.search_text)
                    .where(object_versions_table.c.object_id == target_summary_id)
                    .where(object_versions_table.c.version == 1)
                ).scalar_one()

    assert matches[0].object["id"] == target_summary_id
    assert embedding_count == len(showcase) + len(episode.objects)
    assert isinstance(search_text, str)
    assert target_summary_id in search_text


def test_postgres_write_raw_persists_direct_provenance() -> None:
    assert POSTGRES_DSN is not None

    with temporary_postgres_database(POSTGRES_DSN, prefix="mind_phase_h_pg") as database_dsn:
        run_postgres_migrations(database_dsn)
        with PostgresMemoryStore(database_dsn) as store:
            service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)
            result = service.write_raw(
                {
                    "record_kind": "user_message",
                    "content": {"text": "postgres provenance"},
                    "episode_id": "episode-postgres",
                    "timestamp_order": 1,
                    "direct_provenance": {
                        "producer_kind": "user",
                        "producer_id": "pg-user",
                        "captured_at": "2026-03-08T12:00:00+00:00",
                        "source_channel": "api",
                        "tenant_id": "tenant-pg",
                        "episode_id": "episode-postgres",
                    },
                },
                PrimitiveExecutionContext(
                    actor="phase-h-postgres",
                    budget_scope_id="phase-h-postgres",
                    budget_limit=10.0,
                ),
            )

            assert result.outcome is PrimitiveOutcome.SUCCESS
            assert result.response is not None
            provenance = store.direct_provenance_for_object(result.response["object_id"])

    assert provenance.producer_id == "pg-user"
    assert provenance.source_channel.value == "api"
    assert provenance.tenant_id == "tenant-pg"
    assert provenance.episode_id == "episode-postgres"


def test_postgres_governance_audit_round_trip() -> None:
    assert POSTGRES_DSN is not None

    with temporary_postgres_database(POSTGRES_DSN, prefix="mind_phase_h_audit_pg") as database_dsn:
        run_postgres_migrations(database_dsn)
        with PostgresMemoryStore(database_dsn) as store:
            store.record_governance_audit(
                GovernanceAuditRecord(
                    audit_id="audit-pg-plan-001",
                    operation_id="op-pg-001",
                    action=GovernanceAction.CONCEAL,
                    stage=GovernanceStage.PLAN,
                    actor="pg-governance-operator",
                    capability=GovernanceCapability.GOVERNANCE_PLAN,
                    timestamp=FIXED_TIMESTAMP,
                    outcome=GovernanceOutcome.SUCCEEDED,
                    target_object_ids=["raw-pg-001"],
                    target_provenance_ids=["prov-pg-001"],
                    selection={"producer_id": "user-pg"},
                    summary={"candidate_object_count": 1},
                )
            )

            fetched = store.read_governance_audit("audit-pg-plan-001")
            operation_rows = store.iter_governance_audit_for_operation("op-pg-001")

    assert fetched.actor == "pg-governance-operator"
    assert fetched.capability.value == "governance_plan"
    assert fetched.summary["candidate_object_count"] == 1
    assert [row.audit_id for row in operation_rows] == ["audit-pg-plan-001"]


def test_postgres_concealment_hides_latest_objects() -> None:
    assert POSTGRES_DSN is not None

    showcase = build_core_object_showcase()

    with temporary_postgres_database(
        POSTGRES_DSN,
        prefix="mind_phase_h_conceal_pg",
    ) as database_dsn:
        run_postgres_migrations(database_dsn)
        with PostgresMemoryStore(database_dsn) as store:
            store.insert_objects(showcase)
            store.record_concealment(
                ConcealmentRecord(
                    concealment_id="conceal-pg-001",
                    operation_id="op-pg-conceal-001",
                    object_id="showcase-summary",
                    actor="pg-governance-operator",
                    concealed_at=FIXED_TIMESTAMP,
                    reason="postgres conceal regression",
                )
            )

            visible_summaries = store.iter_latest_objects(object_types=["SummaryNote"])

    assert all(obj["id"] != "showcase-summary" for obj in visible_summaries)


def test_postgres_concealed_episode_replay_excludes_raw_records() -> None:
    assert POSTGRES_DSN is not None

    episode = build_golden_episode_set()[1]
    raw_records = [obj for obj in episode.objects if obj["type"] == "RawRecord"]
    concealed_raw_id = raw_records[-1]["id"]
    visible_raw_ids = [record["id"] for record in raw_records[:-1]]

    with temporary_postgres_database(
        POSTGRES_DSN,
        prefix="mind_phase_h_conceal_replay_pg",
    ) as database_dsn:
        run_postgres_migrations(database_dsn)
        with PostgresMemoryStore(database_dsn) as store:
            store.insert_objects(episode.objects)
            store.record_concealment(
                ConcealmentRecord(
                    concealment_id="conceal-pg-replay-001",
                    operation_id="op-pg-conceal-replay-001",
                    object_id=concealed_raw_id,
                    actor="pg-governance-operator",
                    concealed_at=FIXED_TIMESTAMP,
                    reason="postgres conceal replay regression",
                )
            )

            replayed = replay_episode(store, episode.episode_id)

    assert [record["id"] for record in replayed] == visible_raw_ids


def test_postgres_phase_d_smoke() -> None:
    assert POSTGRES_DSN is not None

    with temporary_postgres_database(POSTGRES_DSN, prefix="mind_phase_d") as database_dsn:
        run_postgres_migrations(database_dsn)
        store_factory = build_postgres_store_factory(database_dsn)
        result = evaluate_phase_d_smoke(Path("phase_d.pg"), store_factory=store_factory)

    assert result.phase_d_smoke_pass
    assert result.smoke_case_count == 12
    assert result.benchmark_case_count == 100
    assert result.answer_benchmark_case_count == 100
    assert result.candidate_recall_at_20 == 1.0
    assert result.workspace_gold_fact_coverage == 1.0
    assert result.median_token_cost_ratio <= 0.60
    assert result.task_success_drop_pp == 0.0
    assert result.task_success_proxy_drop_pp == 0.0


def test_postgres_offline_job_lifecycle() -> None:
    assert POSTGRES_DSN is not None

    with temporary_postgres_database(POSTGRES_DSN, prefix="mind_phase_e") as database_dsn:
        run_postgres_migrations(database_dsn)
        with PostgresMemoryStore(database_dsn) as store:
            store.enqueue_offline_job(
                new_offline_job(
                    job_id="job-late",
                    job_kind=OfflineJobKind.REFLECT_EPISODE,
                    payload=ReflectEpisodeJobPayload(
                        episode_id="episode-004",
                        focus="lower priority reflection",
                    ),
                    priority=0.4,
                    now=FIXED_TIMESTAMP,
                )
            )
            store.enqueue_offline_job(
                new_offline_job(
                    job_id="job-now",
                    job_kind=OfflineJobKind.REFLECT_EPISODE,
                    payload=ReflectEpisodeJobPayload(
                        episode_id="episode-008",
                        focus="higher priority reflection",
                    ),
                    priority=0.9,
                    now=FIXED_TIMESTAMP,
                )
            )

            claimed = store.claim_offline_job(
                worker_id="phase-e-worker",
                now=FIXED_TIMESTAMP,
                job_kinds=[OfflineJobKind.REFLECT_EPISODE],
            )
            assert claimed is not None
            assert claimed.job_id == "job-now"
            assert claimed.status is OfflineJobStatus.RUNNING
            store.complete_offline_job(
                claimed.job_id,
                worker_id="phase-e-worker",
                completed_at=FIXED_TIMESTAMP,
                result={"ok": True},
            )

            next_claim = store.claim_offline_job(
                worker_id="phase-e-worker",
                now=FIXED_TIMESTAMP,
                job_kinds=[OfflineJobKind.REFLECT_EPISODE],
            )
            assert next_claim is not None
            assert next_claim.job_id == "job-late"
            store.fail_offline_job(
                next_claim.job_id,
                worker_id="phase-e-worker",
                failed_at=FIXED_TIMESTAMP,
                error={"message": "expected failure"},
            )

            jobs = store.iter_offline_jobs()

    assert [job.job_id for job in jobs] == ["job-late", "job-now"]
    assert [job.status for job in jobs] == [
        OfflineJobStatus.FAILED,
        OfflineJobStatus.SUCCEEDED,
    ]


def test_postgres_phase_e_gate() -> None:
    assert POSTGRES_DSN is not None

    with temporary_postgres_database(POSTGRES_DSN, prefix="mind_phase_e_gate") as database_dsn:
        run_postgres_migrations(database_dsn)
        store_factory = build_postgres_store_factory(database_dsn)
        result = evaluate_phase_e_gate(Path("phase_e.pg"), store_factory=store_factory)

    assert result.phase_e_pass
    assert result.integrity_report.source_trace_coverage == 1.0
    assert result.startup_result.replay_lift >= 1.5
    assert result.startup_result.schema_validation_precision >= 0.85
    assert result.startup_result.promotion_precision_at_10 >= 0.80
    assert result.dev_eval.pus_improvement >= 0.05
    assert result.dev_eval.pollution_rate_delta <= 0.02
