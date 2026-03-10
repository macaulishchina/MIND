"""Project CLI entry points."""

from __future__ import annotations

import argparse
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from .eval import (
    FixedSummaryMemoryBaselineSystem,
    LongHorizonBenchmarkRunner,
    MindLongHorizonSystem,
    NoMemoryBaselineSystem,
    OptimizedMindStrategy,
    PlainRagBaselineSystem,
    assert_phase_f_comparison,
    assert_phase_f_gate,
    assert_phase_g_gate,
    build_benchmark_suite_report,
    evaluate_fixed_rule_cost_report,
    evaluate_phase_f_comparison,
    evaluate_phase_f_gate,
    evaluate_phase_g_gate,
    write_benchmark_suite_report_json,
    write_phase_f_comparison_report_json,
    write_phase_f_gate_report_json,
    write_phase_g_cost_report_json,
    write_phase_g_gate_report_json,
)
from .fixtures.long_horizon_eval import (
    build_long_horizon_eval_manifest_v1,
    build_long_horizon_eval_v1,
)
from .governance import (
    assert_phase_h_gate,
    evaluate_phase_h_gate,
    write_phase_h_gate_report_json,
)
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


def phase_h_gate_main(argv: Sequence[str] | None = None) -> int:
    """Run the local Phase H provenance foundation gate."""

    parser = argparse.ArgumentParser(
        prog="mind-phase-h-gate",
        description="Run the full local Phase H provenance foundation gate.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/phase_h/gate_report.json",
        help="Output path for the persisted Phase H gate JSON report.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    with tempfile.TemporaryDirectory() as tmpdir:
        result = evaluate_phase_h_gate(Path(tmpdir) / "phase_h_gate.sqlite3")

    try:
        assert_phase_h_gate(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    output_path = write_phase_h_gate_report_json(args.output, result)
    print("Phase H gate report")
    print(f"report_path={output_path}")
    print(
        "direct_provenance_bindings="
        f"{result.authoritative_binding_count}/{result.raw_object_count}"
    )
    print(f"orphan_provenance_rows={result.orphan_provenance_count}")
    print(
        "low_privilege_blocks="
        f"{result.low_privilege_block_count}/{result.low_privilege_total}"
    )
    print(
        "privileged_summaries="
        f"{result.privileged_summary_count}/{result.privileged_total}"
    )
    print(
        "online_conceal_blocks="
        f"{result.online_conceal_block_count}/{result.online_conceal_total}"
    )
    print(
        "offline_conceal_blocks="
        f"{result.offline_conceal_block_count}/{result.offline_conceal_total}"
    )
    print(
        "governance_stage_sequence="
        f"{','.join(result.governance_audit_stage_sequence)}"
    )
    print(f"provenance_query_hit_count={result.provenance_query_hit_count}")
    print(f"H-1={'PASS' if result.h1_pass else 'FAIL'}")
    print(f"H-2={'PASS' if result.h2_pass else 'FAIL'}")
    print(f"H-3={'PASS' if result.h3_pass else 'FAIL'}")
    print(f"H-4={'PASS' if result.h4_pass else 'FAIL'}")
    print(f"H-5={'PASS' if result.h5_pass else 'FAIL'}")
    print(f"H-6={'PASS' if result.h6_pass else 'FAIL'}")
    print(f"H-7={'PASS' if result.h7_pass else 'FAIL'}")
    print(f"H-8={'PASS' if result.h8_pass else 'FAIL'}")
    print(f"phase_h_gate={'PASS' if result.phase_h_pass else 'FAIL'}")
    return 0


def phase_f_manifest_main() -> int:
    """Print the frozen LongHorizonEval v1 manifest."""

    manifest = build_long_horizon_eval_manifest_v1()
    family_counts = ",".join(f"{family}:{count}" for family, count in manifest.family_counts)
    print("Phase F eval manifest")
    print(f"fixture_name={manifest.fixture_name}")
    print(f"fixture_hash={manifest.fixture_hash}")
    print(f"sequence_count={manifest.sequence_count}")
    print(f"step_range={manifest.min_step_count}..{manifest.max_step_count}")
    print(f"family_counts={family_counts}")
    return 0


def phase_f_baselines_main() -> int:
    """Run the three frozen Phase F baselines once on LongHorizonEval v1."""

    sequences = build_long_horizon_eval_v1()
    manifest = build_long_horizon_eval_manifest_v1()
    runner = LongHorizonBenchmarkRunner(sequences=sequences, manifest=manifest)
    runs = (
        runner.run_once(system_id="no_memory", system=NoMemoryBaselineSystem()),
        runner.run_once(
            system_id="fixed_summary_memory",
            system=FixedSummaryMemoryBaselineSystem(),
        ),
        runner.run_once(system_id="plain_rag", system=PlainRagBaselineSystem()),
    )

    print("Phase F baseline report")
    print(f"fixture_name={manifest.fixture_name}")
    print(f"fixture_hash={manifest.fixture_hash}")
    print(f"sequence_count={manifest.sequence_count}")
    for run in runs:
        print(f"{run.system_id}_task_success_rate={run.average_task_success_rate:.2f}")
        print(f"{run.system_id}_gold_fact_coverage={run.average_gold_fact_coverage:.2f}")
        print(f"{run.system_id}_reuse_rate={run.average_reuse_rate:.2f}")
        print(f"{run.system_id}_context_cost_ratio={run.average_context_cost_ratio:.2f}")
        print(f"{run.system_id}_maintenance_cost_ratio={run.average_maintenance_cost_ratio:.2f}")
        print(f"{run.system_id}_pollution_rate={run.average_pollution_rate:.2f}")
        print(f"{run.system_id}_pus={run.average_pus:.2f}")
    print("phase_f_baselines=PASS")
    return 0


def phase_f_report_main(argv: Sequence[str] | None = None) -> int:
    """Run repeated Phase F baselines and persist the CI report."""

    parser = argparse.ArgumentParser(
        prog="mind-phase-f-report",
        description="Run repeated Phase F baselines and persist a 95% CI report.",
    )
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="Independent run count for each system. Must be >= 3 for F-3.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/phase_f/baseline_report.json",
        help="Output path for the persisted JSON report.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.repeat_count < 3:
        raise SystemExit("--repeat-count must be >= 3.")

    sequences = build_long_horizon_eval_v1()
    manifest = build_long_horizon_eval_manifest_v1()
    runner = LongHorizonBenchmarkRunner(sequences=sequences, manifest=manifest)
    report = build_benchmark_suite_report(
        runs_by_system={
            "no_memory": runner.run_many(
                system_id="no_memory",
                system=NoMemoryBaselineSystem(),
                repeat_count=args.repeat_count,
            ),
            "fixed_summary_memory": runner.run_many(
                system_id="fixed_summary_memory",
                system=FixedSummaryMemoryBaselineSystem(),
                repeat_count=args.repeat_count,
            ),
            "plain_rag": runner.run_many(
                system_id="plain_rag",
                system=PlainRagBaselineSystem(),
                repeat_count=args.repeat_count,
            ),
        }
    )
    output_path = write_benchmark_suite_report_json(args.output, report)

    print("Phase F CI report")
    print(f"fixture_name={report.fixture_name}")
    print(f"fixture_hash={report.fixture_hash}")
    print(f"repeat_count={report.repeat_count}")
    print(f"report_path={output_path}")
    for system_report in report.system_reports:
        print(f"{system_report.system_id}_pus_mean={system_report.pus.mean:.2f}")
        print(
            f"{system_report.system_id}_pus_ci="
            f"{system_report.pus.ci_lower:.2f}..{system_report.pus.ci_upper:.2f}"
        )
        print(
            f"{system_report.system_id}_task_success_ci="
            f"{system_report.task_success_rate.ci_lower:.2f}"
            f"..{system_report.task_success_rate.ci_upper:.2f}"
        )
    print("phase_f_report=PASS")
    return 0


def phase_f_comparison_main(argv: Sequence[str] | None = None) -> int:
    """Run the current MIND system against the Phase F baselines."""

    parser = argparse.ArgumentParser(
        prog="mind-phase-f-comparison",
        description="Run Phase F benchmark comparison for F-4 ~ F-6.",
    )
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="Independent run count for each system. Must be >= 3.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/phase_f/comparison_report.json",
        help="Output path for the persisted comparison JSON report.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = evaluate_phase_f_comparison(repeat_count=args.repeat_count)
    try:
        assert_phase_f_comparison(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    output_path = write_phase_f_comparison_report_json(args.output, result)
    mind_report = next(
        system_report
        for system_report in result.suite_report.system_reports
        if system_report.system_id == "mind"
    )
    print("Phase F comparison report")
    print(f"fixture_name={result.suite_report.fixture_name}")
    print(f"fixture_hash={result.suite_report.fixture_hash}")
    print(f"repeat_count={result.suite_report.repeat_count}")
    print(f"report_path={output_path}")
    print(f"mind_pus_mean={mind_report.pus.mean:.2f}")
    print(
        "mind_vs_no_memory_diff="
        f"{result.versus_no_memory.mean_diff:.2f}"
        f" ({result.versus_no_memory.ci_lower:.2f}..{result.versus_no_memory.ci_upper:.2f})"
    )
    print(
        "mind_vs_fixed_summary_memory_diff="
        f"{result.versus_fixed_summary_memory.mean_diff:.2f}"
        f" ({result.versus_fixed_summary_memory.ci_lower:.2f}"
        f"..{result.versus_fixed_summary_memory.ci_upper:.2f})"
    )
    print(
        "mind_vs_plain_rag_diff="
        f"{result.versus_plain_rag.mean_diff:.2f}"
        f" ({result.versus_plain_rag.ci_lower:.2f}..{result.versus_plain_rag.ci_upper:.2f})"
    )
    print(f"F-2={'PASS' if result.f2_pass else 'FAIL'}")
    print(f"F-3={'PASS' if result.f3_pass else 'FAIL'}")
    print(f"F-4={'PASS' if result.f4_pass else 'FAIL'}")
    print(f"F-5={'PASS' if result.f5_pass else 'FAIL'}")
    print(f"F-6={'PASS' if result.f6_pass else 'FAIL'}")
    print(f"phase_f_comparison={'PASS' if result.phase_f_comparison_pass else 'FAIL'}")
    return 0


def phase_f_gate_main(argv: Sequence[str] | None = None) -> int:
    """Run the full local Phase F gate, including F-7 ablations."""

    parser = argparse.ArgumentParser(
        prog="mind-phase-f-gate",
        description="Run the full local Phase F gate.",
    )
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="Independent run count for each system. Must be >= 3.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/phase_f/gate_report.json",
        help="Output path for the persisted gate JSON report.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = evaluate_phase_f_gate(repeat_count=args.repeat_count)
    try:
        assert_phase_f_gate(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    output_path = write_phase_f_gate_report_json(args.output, result)
    print("Phase F gate report")
    print(f"manifest_hash={result.manifest_hash}")
    print(
        "manifest_step_range="
        f"{result.manifest_min_step_count}..{result.manifest_max_step_count}"
    )
    print(f"repeat_count={result.comparison_result.suite_report.repeat_count}")
    print(f"report_path={output_path}")
    print(
        "mind_vs_no_memory_diff="
        f"{result.comparison_result.versus_no_memory.mean_diff:.2f}"
    )
    print(
        "mind_vs_fixed_summary_memory_diff="
        f"{result.comparison_result.versus_fixed_summary_memory.mean_diff:.2f}"
    )
    print(
        "mind_vs_plain_rag_diff="
        f"{result.comparison_result.versus_plain_rag.mean_diff:.2f}"
    )
    print(f"workspace_ablation_drop={result.workspace_ablation.mean_diff:.2f}")
    print(
        "offline_maintenance_ablation_drop="
        f"{result.offline_maintenance_ablation.mean_diff:.2f}"
    )
    print(f"F-1={'PASS' if result.f1_pass else 'FAIL'}")
    print(f"F-2={'PASS' if result.f2_pass else 'FAIL'}")
    print(f"F-3={'PASS' if result.f3_pass else 'FAIL'}")
    print(f"F-4={'PASS' if result.f4_pass else 'FAIL'}")
    print(f"F-5={'PASS' if result.f5_pass else 'FAIL'}")
    print(f"F-6={'PASS' if result.f6_pass else 'FAIL'}")
    print(f"F-7={'PASS' if result.f7_pass else 'FAIL'}")
    print(f"phase_f_gate={'PASS' if result.phase_f_pass else 'FAIL'}")
    return 0


def phase_g_cost_report_main(argv: Sequence[str] | None = None) -> int:
    """Run the Phase G fixed-rule strategy cost report skeleton."""

    parser = argparse.ArgumentParser(
        prog="mind-phase-g-cost-report",
        description="Run the Phase G fixed-rule strategy cost report skeleton.",
    )
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="Independent run count for cost accounting. Must be >= 1.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/phase_g/cost_report.json",
        help="Output path for the persisted Phase G cost report JSON.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = evaluate_fixed_rule_cost_report(repeat_count=args.repeat_count)
    output_path = write_phase_g_cost_report_json(args.output, result)
    print("Phase G cost report")
    print(f"fixture_name={result.fixture_name}")
    print(f"fixture_hash={result.fixture_hash}")
    print(f"strategy_id={result.strategy_id}")
    print(f"repeat_count={result.repeat_count}")
    print(f"report_path={output_path}")
    print(f"token_cost_ratio={result.token_cost_ratio.mean:.2f}")
    print(f"storage_cost_ratio={result.storage_cost_ratio.mean:.2f}")
    print(f"maintenance_cost_ratio={result.maintenance_cost_ratio.mean:.2f}")
    print(f"total_cost_ratio={result.total_cost_ratio.mean:.2f}")
    print(f"total_budget_ratio={result.budget_profile.total_budget_ratio:.2f}")
    print(f"total_budget_bias={result.total_budget_bias.mean:.2f}")
    print("phase_g_cost_report=PASS")
    return 0


def phase_g_strategy_dev_main(argv: Sequence[str] | None = None) -> int:
    """Run a local fixed-rule vs optimized-v1 dev comparison."""

    parser = argparse.ArgumentParser(
        prog="mind-phase-g-strategy-dev",
        description="Run a Phase G dev comparison between fixed-rule and optimized_v1.",
    )
    parser.add_argument(
        "--run-id",
        type=int,
        default=1,
        help="Deterministic run id used by both systems.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    runner = LongHorizonBenchmarkRunner(
        sequences=build_long_horizon_eval_v1(),
        manifest=build_long_horizon_eval_manifest_v1(),
    )
    fixed_system = MindLongHorizonSystem()
    optimized_system = MindLongHorizonSystem(strategy=OptimizedMindStrategy())
    try:
        fixed_run = runner.run_once(
            system_id="mind_fixed_rule",
            system=fixed_system,
            run_id=args.run_id,
        )
        optimized_run = runner.run_once(
            system_id="mind_optimized_v1",
            system=optimized_system,
            run_id=args.run_id,
        )
        fixed_snapshot = fixed_system.cost_snapshot(args.run_id)
        optimized_snapshot = optimized_system.cost_snapshot(args.run_id)
    finally:
        fixed_system.close()
        optimized_system.close()

    print("Phase G strategy dev report")
    print(f"fixture_name={fixed_run.fixture_name}")
    print(f"fixture_hash={fixed_run.fixture_hash}")
    print(f"run_id={args.run_id}")
    print(f"fixed_rule_pus={fixed_run.average_pus:.2f}")
    print(f"optimized_v1_pus={optimized_run.average_pus:.2f}")
    print(f"pus_delta={optimized_run.average_pus - fixed_run.average_pus:.2f}")
    print(f"fixed_rule_context_cost_ratio={fixed_run.average_context_cost_ratio:.2f}")
    print(f"optimized_v1_context_cost_ratio={optimized_run.average_context_cost_ratio:.2f}")
    print(f"fixed_rule_storage_cost_ratio={fixed_snapshot.storage_cost_ratio:.2f}")
    print(f"optimized_v1_storage_cost_ratio={optimized_snapshot.storage_cost_ratio:.2f}")
    print(
        "phase_g_strategy_dev="
        f"{'PASS' if optimized_run.average_pus > fixed_run.average_pus else 'FAIL'}"
    )
    return 0


def phase_g_gate_main(argv: Sequence[str] | None = None) -> int:
    """Run the formal Phase G local gate."""

    parser = argparse.ArgumentParser(
        prog="mind-phase-g-gate",
        description="Run the full local Phase G strategy optimization gate.",
    )
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="Independent run count for each system. Must be >= 3.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/phase_g/gate_report.json",
        help="Output path for the persisted Phase G gate JSON report.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = evaluate_phase_g_gate(repeat_count=args.repeat_count)
    try:
        assert_phase_g_gate(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    output_path = write_phase_g_gate_report_json(args.output, result)
    print("Phase G gate report")
    print(f"manifest_hash={result.manifest_hash}")
    print(f"repeat_count={result.repeat_count}")
    print(f"report_path={output_path}")
    print(f"pus_improvement={result.pus_improvement.mean_diff:.2f}")
    for family_result in result.family_improvements:
        print(f"{family_result.family}_pus_delta={family_result.pus_delta.mean_diff:.2f}")
    print(f"token_budget_bias={result.optimized_cost_report.token_budget_bias.mean:.2f}")
    print(f"storage_budget_bias={result.optimized_cost_report.storage_budget_bias.mean:.2f}")
    print(
        "maintenance_budget_bias="
        f"{result.optimized_cost_report.maintenance_budget_bias.mean:.2f}"
    )
    print(f"total_budget_bias={result.optimized_cost_report.total_budget_bias.mean:.2f}")
    print(f"pollution_rate_delta={result.pollution_rate_delta.mean_diff:.2f}")
    print(f"G-1={'PASS' if result.g1_pass else 'FAIL'}")
    print(f"G-2={'PASS' if result.g2_pass else 'FAIL'}")
    print(f"G-3={'PASS' if result.g3_pass else 'FAIL'}")
    print(f"G-4={'PASS' if result.g4_pass else 'FAIL'}")
    print(f"G-5={'PASS' if result.g5_pass else 'FAIL'}")
    print(f"phase_g_gate={'PASS' if result.phase_g_pass else 'FAIL'}")
    return 0
