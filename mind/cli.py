"""Project CLI entry points."""

from __future__ import annotations

import argparse
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from .kernel.phase_b import assert_phase_b_gate, evaluate_phase_b_gate
from .kernel.postgres_store import (
    PostgresMemoryStore,
    build_postgres_store_factory,
    run_postgres_migrations,
    temporary_postgres_database,
)
from .offline import (
    OfflineJobKind,
    OfflineJobStatus,
    OfflineMaintenanceService,
    OfflineWorker,
    assert_phase_e_gate,
    assert_phase_e_startup,
    evaluate_phase_e_gate,
    evaluate_phase_e_startup,
)
from .primitives.phase_c import assert_phase_c_gate, evaluate_phase_c_gate
from .workspace import assert_phase_d_smoke, evaluate_phase_d_smoke


def phase_b_gate_main() -> int:
    """Run the local Phase B gate baseline check."""

    with tempfile.TemporaryDirectory() as tmpdir:
        result = evaluate_phase_b_gate(Path(tmpdir) / "phase_b.sqlite3")

    try:
        assert_phase_b_gate(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    print("Phase B gate baseline report")
    print(f"golden_episodes={result.golden_episode_count}")
    print(f"core_object_types={result.core_object_type_count}")
    print(f"round_trip_objects={result.round_trip_match_count}/{result.round_trip_total}")
    print(f"replay_matches={result.replay_match_count}/{result.replay_total}")
    print(f"source_trace_coverage={result.integrity_report.source_trace_coverage:.2f}")
    print(f"metadata_coverage={result.integrity_report.metadata_coverage:.2f}")
    print(f"dangling_refs={len(result.integrity_report.dangling_refs)}")
    print(f"cycles={len(result.integrity_report.cycles)}")
    print(f"version_chain_issues={len(result.integrity_report.version_chain_issues)}")
    print(f"B-1={'PASS' if result.b1_pass else 'FAIL'}")
    print(f"B-2={'PASS' if result.b2_pass else 'FAIL'}")
    print(f"B-3={'PASS' if result.b3_pass else 'FAIL'}")
    print(f"B-4={'PASS' if result.b4_pass else 'FAIL'}")
    print(f"B-5={'PASS' if result.b5_pass else 'FAIL'}")
    print(f"phase_b_gate={'PASS' if result.phase_b_pass else 'FAIL'}")
    return 0


def phase_c_gate_main() -> int:
    """Run the local Phase C gate baseline check."""

    with tempfile.TemporaryDirectory() as tmpdir:
        result = evaluate_phase_c_gate(Path(tmpdir) / "phase_c.sqlite3")

    try:
        assert_phase_c_gate(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    print("Phase C gate baseline report")
    print(f"primitive_golden_calls={result.total_calls}")
    print(f"expectation_matches={result.expectation_match_count}/{result.total_calls}")
    print(f"schema_valid_calls={result.schema_valid_calls}/{result.total_calls}")
    print(f"structured_log_calls={result.structured_log_calls}/{result.total_calls}")
    print(f"smoke_coverage={result.smoke_success_count}/7")
    print(
        "budget_rejections="
        f"{result.budget_rejection_match_count}/{result.budget_total}"
    )
    print(f"rollback_atomic={result.rollback_atomic_count}/{result.rollback_total}")
    print(f"C-1={'PASS' if result.c1_pass else 'FAIL'}")
    print(f"C-2={'PASS' if result.c2_pass else 'FAIL'}")
    print(f"C-3={'PASS' if result.c3_pass else 'FAIL'}")
    print(f"C-4={'PASS' if result.c4_pass else 'FAIL'}")
    print(f"C-5={'PASS' if result.c5_pass else 'FAIL'}")
    print(f"phase_c_gate={'PASS' if result.phase_c_pass else 'FAIL'}")
    return 0


def postgres_regression_main(argv: Sequence[str] | None = None) -> int:
    """Run Phase B/C/D/E checks against a migrated PostgreSQL database."""

    parser = argparse.ArgumentParser(
        prog="mind-postgres-regression",
        description="Run Phase B and Phase C regressions on PostgreSQL.",
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("MIND_POSTGRES_DSN"),
        help="Admin PostgreSQL DSN. Falls back to MIND_POSTGRES_DSN.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.dsn:
        raise SystemExit("Provide --dsn or set MIND_POSTGRES_DSN.")

    with temporary_postgres_database(args.dsn, prefix="mind_phase_b") as database_dsn:
        run_postgres_migrations(database_dsn)
        store_factory = build_postgres_store_factory(database_dsn)
        phase_b_result = evaluate_phase_b_gate(Path("phase_b.pg"), store_factory=store_factory)

    with temporary_postgres_database(args.dsn, prefix="mind_phase_c") as database_dsn:
        run_postgres_migrations(database_dsn)
        store_factory = build_postgres_store_factory(database_dsn)
        phase_c_result = evaluate_phase_c_gate(Path("phase_c.pg"), store_factory=store_factory)

    with temporary_postgres_database(args.dsn, prefix="mind_phase_d") as database_dsn:
        run_postgres_migrations(database_dsn)
        store_factory = build_postgres_store_factory(database_dsn)
        phase_d_result = evaluate_phase_d_smoke(Path("phase_d.pg"), store_factory=store_factory)

    with temporary_postgres_database(args.dsn, prefix="mind_phase_e") as database_dsn:
        run_postgres_migrations(database_dsn)
        store_factory = build_postgres_store_factory(database_dsn)
        phase_e_result = evaluate_phase_e_gate(Path("phase_e.pg"), store_factory=store_factory)

    try:
        assert_phase_b_gate(phase_b_result)
        assert_phase_c_gate(phase_c_result)
        assert_phase_d_smoke(phase_d_result)
        assert_phase_e_gate(phase_e_result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    print("PostgreSQL regression report")
    print("backend=postgresql")
    print(f"phase_b_gate={'PASS' if phase_b_result.phase_b_pass else 'FAIL'}")
    print(f"phase_c_gate={'PASS' if phase_c_result.phase_c_pass else 'FAIL'}")
    print(f"phase_d_smoke={'PASS' if phase_d_result.phase_d_smoke_pass else 'FAIL'}")
    print(f"phase_e_gate={'PASS' if phase_e_result.phase_e_pass else 'FAIL'}")
    print(
        "phase_b_round_trip="
        f"{phase_b_result.round_trip_match_count}/{phase_b_result.round_trip_total}"
    )
    print(f"phase_b_replay={phase_b_result.replay_match_count}/{phase_b_result.replay_total}")
    print(
        "phase_c_schema="
        f"{phase_c_result.schema_valid_calls}/{phase_c_result.total_calls}"
    )
    print(
        "phase_c_budget_rejections="
        f"{phase_c_result.budget_rejection_match_count}/{phase_c_result.budget_total}"
    )
    print(
        "phase_c_rollback_atomic="
        f"{phase_c_result.rollback_atomic_count}/{phase_c_result.rollback_total}"
    )
    print(
        "phase_d_recall_at_20="
        f"{phase_d_result.candidate_recall_at_20:.2f}"
    )
    print(
        "phase_d_workspace_coverage="
        f"{phase_d_result.workspace_gold_fact_coverage:.2f}"
    )
    print(
        "phase_d_workspace_discipline="
        f"{phase_d_result.workspace_slot_discipline_rate:.2f}"
    )
    print(
        "phase_d_token_cost_ratio="
        f"{phase_d_result.median_token_cost_ratio:.2f}"
    )
    print(
        "phase_d_task_success_drop_pp="
        f"{phase_d_result.task_success_drop_pp:.2f}"
    )
    print(f"phase_e_replay_lift={phase_e_result.startup_result.replay_lift:.2f}")
    print(
        "phase_e_schema_validation_precision="
        f"{phase_e_result.startup_result.schema_validation_precision:.2f}"
    )
    print(
        "phase_e_promotion_precision_at_10="
        f"{phase_e_result.startup_result.promotion_precision_at_10:.2f}"
    )
    print(f"phase_e_pus_improvement={phase_e_result.dev_eval.pus_improvement:.2f}")
    print(
        "phase_e_pollution_rate_delta="
        f"{phase_e_result.dev_eval.pollution_rate_delta:.2f}"
    )
    return 0


def phase_d_smoke_main() -> int:
    """Run the local Phase D retrieval/workspace smoke baseline."""

    with tempfile.TemporaryDirectory() as tmpdir:
        result = evaluate_phase_d_smoke(Path(tmpdir) / "phase_d.sqlite3")

    try:
        assert_phase_d_smoke(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    print("Phase D smoke baseline report")
    print(f"retrieval_smoke_cases={result.smoke_case_count}")
    print(f"retrieval_benchmark_cases={result.benchmark_case_count}")
    print(f"answer_benchmark_cases={result.answer_benchmark_case_count}")
    print(
        "mode_smoke_successes="
        f"keyword={result.keyword_smoke_successes},"
        f"time_window={result.time_window_smoke_successes},"
        f"vector={result.vector_smoke_successes}"
    )
    print(f"candidate_recall_at_20={result.candidate_recall_at_20:.2f}")
    print(f"workspace_gold_fact_coverage={result.workspace_gold_fact_coverage:.2f}")
    print(f"workspace_slot_discipline={result.workspace_slot_discipline_rate:.2f}")
    print(f"workspace_source_ref_coverage={result.workspace_source_ref_coverage:.2f}")
    print(f"median_token_cost_ratio={result.median_token_cost_ratio:.2f}")
    print(f"raw_top20_task_success={result.raw_top20_task_success_rate:.2f}")
    print(f"workspace_task_success={result.workspace_task_success_rate:.2f}")
    print(f"task_success_drop_pp={result.task_success_drop_pp:.2f}")
    print(f"raw_top20_answer_quality_score={result.raw_top20_answer_quality_score:.2f}")
    print(f"workspace_answer_quality_score={result.workspace_answer_quality_score:.2f}")
    print(f"raw_top20_task_success_proxy={result.raw_top20_task_success_proxy_rate:.2f}")
    print(f"workspace_task_success_proxy={result.workspace_task_success_proxy_rate:.2f}")
    print(f"task_success_proxy_drop_pp={result.task_success_proxy_drop_pp:.2f}")
    print(f"D-1={'PASS' if result.d1_pass else 'FAIL'}")
    print(f"D-2={'PASS' if result.d2_pass else 'FAIL'}")
    print(f"D-3={'PASS' if result.d3_pass else 'FAIL'}")
    print(f"D-4={'PASS' if result.d4_pass else 'FAIL'}")
    print(f"D-5={'PASS' if result.d5_pass else 'FAIL'}")
    print(f"phase_d_smoke={'PASS' if result.phase_d_smoke_pass else 'FAIL'}")
    return 0


def offline_worker_main(argv: Sequence[str] | None = None) -> int:
    """Run one Phase E offline worker batch against PostgreSQL."""

    parser = argparse.ArgumentParser(
        prog="mind-offline-worker-once",
        description="Run a single offline maintenance worker batch.",
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("MIND_POSTGRES_DSN"),
        help="PostgreSQL DSN. Falls back to MIND_POSTGRES_DSN.",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=1,
        help="Maximum number of jobs to claim in this batch.",
    )
    parser.add_argument(
        "--worker-id",
        default="mind-offline-worker",
        help="Worker identifier to stamp on claimed jobs.",
    )
    parser.add_argument(
        "--job-kind",
        action="append",
        choices=[job_kind.value for job_kind in OfflineJobKind],
        default=[],
        help="Optional job kind filter. May be passed multiple times.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.dsn:
        raise SystemExit("Provide --dsn or set MIND_POSTGRES_DSN.")
    if args.max_jobs < 1:
        raise SystemExit("--max-jobs must be >= 1.")

    with PostgresMemoryStore(args.dsn) as store:
        maintenance_service = OfflineMaintenanceService(store)
        worker = OfflineWorker(
            store,
            maintenance_service,
            worker_id=args.worker_id,
        )
        result = worker.run_once(
            max_jobs=args.max_jobs,
            job_kinds=[OfflineJobKind(job_kind) for job_kind in args.job_kind],
        )
        pending_jobs = len(store.iter_offline_jobs(statuses=[OfflineJobStatus.PENDING]))
        running_jobs = len(store.iter_offline_jobs(statuses=[OfflineJobStatus.RUNNING]))
        succeeded_jobs = len(store.iter_offline_jobs(statuses=[OfflineJobStatus.SUCCEEDED]))
        failed_jobs = len(store.iter_offline_jobs(statuses=[OfflineJobStatus.FAILED]))

    print("Offline worker run report")
    print(f"worker_id={args.worker_id}")
    print(f"claimed_jobs={result.claimed_jobs}")
    print(f"succeeded_jobs={result.succeeded_jobs}")
    print(f"failed_jobs={result.failed_jobs}")
    print(f"completed_job_ids={','.join(result.completed_job_ids)}")
    print(f"pending_jobs={pending_jobs}")
    print(f"running_jobs={running_jobs}")
    print(f"succeeded_jobs_total={succeeded_jobs}")
    print(f"failed_jobs_total={failed_jobs}")
    return 0


def phase_e_startup_main() -> int:
    """Run the local Phase E startup baseline."""

    with tempfile.TemporaryDirectory() as tmpdir:
        result = evaluate_phase_e_startup(Path(tmpdir) / "phase_e.sqlite3")

    try:
        assert_phase_e_startup(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    print("Phase E startup baseline report")
    print(f"long_horizon_sequences={result.sequence_count}")
    print(f"step_range={result.min_step_count}..{result.max_step_count}")
    print(f"promotion_sequences={result.promotion_sequence_count}")
    print(f"top_decile_reuse_rate={result.top_decile_reuse_rate:.2f}")
    print(f"random_decile_reuse_rate={result.random_decile_reuse_rate:.2f}")
    print(f"replay_lift={result.replay_lift:.2f}")
    print(f"audited_schema_count={result.audited_schema_count}")
    print(f"schema_validation_precision={result.schema_validation_precision:.2f}")
    print(f"promotion_precision_at_10={result.promotion_precision_at_10:.2f}")
    print(f"E-startup-1={'PASS' if result.long_horizon_fixture_pass else 'FAIL'}")
    print(f"E-startup-2={'PASS' if result.replay_lift_pass else 'FAIL'}")
    print(f"E-startup-3={'PASS' if result.schema_validation_pass else 'FAIL'}")
    print(f"E-startup-4={'PASS' if result.promotion_precision_pass else 'FAIL'}")
    print(f"phase_e_startup={'PASS' if result.phase_e_startup_pass else 'FAIL'}")
    return 0


def phase_e_gate_main() -> int:
    """Run the local Phase E formal gate."""

    with tempfile.TemporaryDirectory() as tmpdir:
        result = evaluate_phase_e_gate(Path(tmpdir) / "phase_e_gate.sqlite3")

    try:
        assert_phase_e_gate(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    print("Phase E gate report")
    print(f"long_horizon_sequences={result.startup_result.sequence_count}")
    print(f"generated_reflections={result.generated_reflection_count}")
    print(f"generated_schemas={result.generated_schema_count}")
    print(f"source_trace_coverage={result.integrity_report.source_trace_coverage:.2f}")
    print(f"schema_validation_precision={result.startup_result.schema_validation_precision:.2f}")
    print(f"replay_lift={result.startup_result.replay_lift:.2f}")
    print(f"promotion_precision_at_10={result.startup_result.promotion_precision_at_10:.2f}")
    print(f"no_maintenance_pus={result.dev_eval.no_maintenance_pus:.2f}")
    print(f"maintenance_pus={result.dev_eval.maintenance_pus:.2f}")
    print(f"pus_improvement={result.dev_eval.pus_improvement:.2f}")
    print(f"pollution_rate_delta={result.dev_eval.pollution_rate_delta:.2f}")
    print(f"E-1={'PASS' if result.e1_pass else 'FAIL'}")
    print(f"E-2={'PASS' if result.e2_pass else 'FAIL'}")
    print(f"E-3={'PASS' if result.e3_pass else 'FAIL'}")
    print(f"E-4={'PASS' if result.e4_pass else 'FAIL'}")
    print(f"E-5={'PASS' if result.e5_pass else 'FAIL'}")
    print(f"phase_e_gate={'PASS' if result.phase_e_pass else 'FAIL'}")
    return 0
