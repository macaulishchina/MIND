"""Gate and smoke-test CLI entry points (kernel through deployment)."""

from __future__ import annotations

import argparse
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from .access import (
    assert_access_gate,
    evaluate_access_gate,
    write_access_gate_report_json,
)
from .capabilities import (
    assert_capability_gate,
    evaluate_capability_gate,
    evaluate_capability_provider_compatibility_report,
    write_capability_gate_report_json,
    write_capability_provider_compatibility_report_json,
)
from .cli import _LIVE_CAPABILITY_PROVIDER_CHOICES
from .cli_phase_gates import (
    _build_live_capability_adapters,
    _format_live_provider_summary,
)
from .fixtures.product_transport_audit import (
    evaluate_runtime_product_transport_audit_report,
    write_product_transport_audit_json,
    write_product_transport_audit_markdown,
)
from .governance import (
    assert_governance_gate,
    evaluate_governance_gate,
    write_governance_gate_report_json,
)
from .kernel.gate import assert_kernel_gate, evaluate_kernel_gate
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
    assert_offline_gate,
    assert_offline_startup,
    evaluate_offline_gate,
    evaluate_offline_startup,
)
from .primitives.gate import assert_primitive_gate, evaluate_primitive_gate
from .workspace import assert_workspace_smoke, evaluate_workspace_smoke


def kernel_gate_main() -> int:
    """Run the local Phase B gate baseline check."""

    with tempfile.TemporaryDirectory() as tmpdir:
        result = evaluate_kernel_gate(Path(tmpdir) / "phase_b.sqlite3")

    try:
        assert_kernel_gate(result)
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
    print(f"phase_b_gate={'PASS' if result.kernel_gate_pass else 'FAIL'}")
    return 0


def primitive_gate_main() -> int:
    """Run the local Phase C gate baseline check."""

    with tempfile.TemporaryDirectory() as tmpdir:
        result = evaluate_primitive_gate(Path(tmpdir) / "phase_c.sqlite3")

    try:
        assert_primitive_gate(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    print("Phase C gate baseline report")
    print(f"primitive_golden_calls={result.total_calls}")
    print(f"expectation_matches={result.expectation_match_count}/{result.total_calls}")
    print(f"schema_valid_calls={result.schema_valid_calls}/{result.total_calls}")
    print(f"structured_log_calls={result.structured_log_calls}/{result.total_calls}")
    print(f"smoke_coverage={result.smoke_success_count}/7")
    print(f"budget_rejections={result.budget_rejection_match_count}/{result.budget_total}")
    print(f"rollback_atomic={result.rollback_atomic_count}/{result.rollback_total}")
    print(f"C-1={'PASS' if result.c1_pass else 'FAIL'}")
    print(f"C-2={'PASS' if result.c2_pass else 'FAIL'}")
    print(f"C-3={'PASS' if result.c3_pass else 'FAIL'}")
    print(f"C-4={'PASS' if result.c4_pass else 'FAIL'}")
    print(f"C-5={'PASS' if result.c5_pass else 'FAIL'}")
    print(f"phase_c_gate={'PASS' if result.primitive_gate_pass else 'FAIL'}")
    return 0


def postgres_regression_main(argv: Sequence[str] | None = None) -> int:
    """Run Phase B/C/D/E checks against a migrated PostgreSQL database."""

    parser = argparse.ArgumentParser(
        prog="mindtest-postgres-regression",
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

    with temporary_postgres_database(args.dsn, prefix="mind_kernel") as database_dsn:
        run_postgres_migrations(database_dsn)
        store_factory = build_postgres_store_factory(database_dsn)
        kernel_result = evaluate_kernel_gate(Path("kernel.pg"), store_factory=store_factory)

    with temporary_postgres_database(args.dsn, prefix="mind_primitive") as database_dsn:
        run_postgres_migrations(database_dsn)
        store_factory = build_postgres_store_factory(database_dsn)
        primitive_result = evaluate_primitive_gate(
            Path("primitive.pg"),
            store_factory=store_factory,
        )

    with temporary_postgres_database(args.dsn, prefix="mind_workspace") as database_dsn:
        run_postgres_migrations(database_dsn)
        store_factory = build_postgres_store_factory(database_dsn)
        workspace_result = evaluate_workspace_smoke(
            Path("workspace.pg"),
            store_factory=store_factory,
        )

    with temporary_postgres_database(args.dsn, prefix="mind_offline") as database_dsn:
        run_postgres_migrations(database_dsn)
        store_factory = build_postgres_store_factory(database_dsn)
        offline_result = evaluate_offline_gate(Path("offline.pg"), store_factory=store_factory)

    try:
        assert_kernel_gate(kernel_result)
        assert_primitive_gate(primitive_result)
        assert_workspace_smoke(workspace_result)
        assert_offline_gate(offline_result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    print("PostgreSQL regression report")
    print("backend=postgresql")
    print(f"phase_b_gate={'PASS' if kernel_result.kernel_gate_pass else 'FAIL'}")
    print(f"phase_c_gate={'PASS' if primitive_result.primitive_gate_pass else 'FAIL'}")
    print(f"phase_d_smoke={'PASS' if workspace_result.workspace_smoke_pass else 'FAIL'}")
    print(f"phase_e_gate={'PASS' if offline_result.offline_gate_pass else 'FAIL'}")
    print(
        "phase_b_round_trip="
        f"{kernel_result.round_trip_match_count}/{kernel_result.round_trip_total}"
    )
    print(f"phase_b_replay={kernel_result.replay_match_count}/{kernel_result.replay_total}")
    print(f"phase_c_schema={primitive_result.schema_valid_calls}/{primitive_result.total_calls}")
    print(
        "phase_c_budget_rejections="
        f"{primitive_result.budget_rejection_match_count}/{primitive_result.budget_total}"
    )
    print(
        "phase_c_rollback_atomic="
        f"{primitive_result.rollback_atomic_count}/{primitive_result.rollback_total}"
    )
    print(f"phase_d_recall_at_20={workspace_result.candidate_recall_at_20:.2f}")
    print(f"phase_d_workspace_coverage={workspace_result.workspace_gold_fact_coverage:.2f}")
    print(f"phase_d_workspace_discipline={workspace_result.workspace_slot_discipline_rate:.2f}")
    print(f"phase_d_token_cost_ratio={workspace_result.median_token_cost_ratio:.2f}")
    print(f"phase_d_task_success_drop_pp={workspace_result.task_success_drop_pp:.2f}")
    print(f"phase_e_replay_lift={offline_result.startup_result.replay_lift:.2f}")
    print(
        "phase_e_schema_validation_precision="
        f"{offline_result.startup_result.schema_validation_precision:.2f}"
    )
    print(
        "phase_e_promotion_precision_at_10="
        f"{offline_result.startup_result.promotion_precision_at_10:.2f}"
    )
    print(f"phase_e_pus_improvement={offline_result.dev_eval.pus_improvement:.2f}")
    print(f"phase_e_pollution_rate_delta={offline_result.dev_eval.pollution_rate_delta:.2f}")
    return 0


def workspace_smoke_main() -> int:
    """Run the local Phase D retrieval/workspace smoke baseline."""

    with tempfile.TemporaryDirectory() as tmpdir:
        result = evaluate_workspace_smoke(Path(tmpdir) / "phase_d.sqlite3")

    try:
        assert_workspace_smoke(result)
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
    print(f"phase_d_smoke={'PASS' if result.workspace_smoke_pass else 'FAIL'}")
    return 0


def offline_worker_main(argv: Sequence[str] | None = None) -> int:
    """Run one Phase E offline worker batch against PostgreSQL."""

    parser = argparse.ArgumentParser(
        prog="mindtest-offline-worker-once",
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


def offline_startup_main() -> int:
    """Run the local Phase E startup baseline."""

    with tempfile.TemporaryDirectory() as tmpdir:
        result = evaluate_offline_startup(Path(tmpdir) / "phase_e.sqlite3")

    try:
        assert_offline_startup(result)
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
    print(f"phase_e_startup={'PASS' if result.offline_startup_pass else 'FAIL'}")
    return 0


def offline_gate_main() -> int:
    """Run the local Phase E formal gate."""

    with tempfile.TemporaryDirectory() as tmpdir:
        result = evaluate_offline_gate(Path(tmpdir) / "phase_e_gate.sqlite3")

    try:
        assert_offline_gate(result)
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
    print(f"phase_e_gate={'PASS' if result.offline_gate_pass else 'FAIL'}")
    return 0


def governance_gate_main(argv: Sequence[str] | None = None) -> int:
    """Run the local Phase H provenance foundation gate."""

    parser = argparse.ArgumentParser(
        prog="mindtest-phase-h-gate",
        description="Run the full local Phase H provenance foundation gate.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/phase_h/gate_report.json",
        help="Output path for the persisted Phase H gate JSON report.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    with tempfile.TemporaryDirectory() as tmpdir:
        result = evaluate_governance_gate(Path(tmpdir) / "phase_h_gate.sqlite3")

    try:
        assert_governance_gate(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    output_path = write_governance_gate_report_json(args.output, result)
    print("Phase H gate report")
    print(f"report_path={output_path}")
    print(
        f"direct_provenance_bindings={result.authoritative_binding_count}/{result.raw_object_count}"
    )
    print(f"orphan_provenance_rows={result.orphan_provenance_count}")
    print(f"low_privilege_blocks={result.low_privilege_block_count}/{result.low_privilege_total}")
    print(f"privileged_summaries={result.privileged_summary_count}/{result.privileged_total}")
    print(
        f"online_conceal_blocks={result.online_conceal_block_count}/{result.online_conceal_total}"
    )
    print(
        "offline_conceal_blocks="
        f"{result.offline_conceal_block_count}/{result.offline_conceal_total}"
    )
    print(f"governance_stage_sequence={','.join(result.governance_audit_stage_sequence)}")
    print(f"provenance_query_hit_count={result.provenance_query_hit_count}")
    print(f"H-1={'PASS' if result.h1_pass else 'FAIL'}")
    print(f"H-2={'PASS' if result.h2_pass else 'FAIL'}")
    print(f"H-3={'PASS' if result.h3_pass else 'FAIL'}")
    print(f"H-4={'PASS' if result.h4_pass else 'FAIL'}")
    print(f"H-5={'PASS' if result.h5_pass else 'FAIL'}")
    print(f"H-6={'PASS' if result.h6_pass else 'FAIL'}")
    print(f"H-7={'PASS' if result.h7_pass else 'FAIL'}")
    print(f"H-8={'PASS' if result.h8_pass else 'FAIL'}")
    print(f"phase_h_gate={'PASS' if result.governance_gate_pass else 'FAIL'}")
    return 0


def access_gate_main(argv: Sequence[str] | None = None) -> int:
    """Run the local Phase I runtime access gate."""

    parser = argparse.ArgumentParser(
        prog="mindtest-phase-i-gate",
        description="Run the full local Phase I runtime access gate.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/phase_i/gate_report.json",
        help="Output path for the persisted Phase I gate JSON report.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    with tempfile.TemporaryDirectory() as tmpdir:
        result = evaluate_access_gate(Path(tmpdir) / "phase_i_gate.sqlite3")

    try:
        assert_access_gate(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    output_path = write_access_gate_report_json(args.output, result)
    print("Phase I gate report")
    print(f"report_path={output_path}")
    print(f"benchmark_cases={result.case_count}")
    print(f"benchmark_runs={result.benchmark_run_count}")
    print(f"callable_modes={','.join(mode.value for mode in result.callable_modes)}")
    print(f"trace_coverage={result.trace_coverage_count}/{result.trace_total}")
    print(
        "flash_floor="
        f"time_budget_hit_rate:{result.flash_time_budget_hit_rate:.2f},"
        f"constraint_satisfaction:{result.flash_constraint_satisfaction:.2f}"
    )
    print(
        "recall_floor="
        f"aqs:{result.recall_answer_quality_score:.2f},"
        f"mus:{result.recall_memory_use_score:.2f}"
    )
    print(
        "reconstruct_floor="
        f"faithfulness:{result.reconstruct_answer_faithfulness:.2f},"
        f"gold_fact_coverage:{result.reconstruct_gold_fact_coverage:.2f}"
    )
    print(
        "reflective_floor="
        f"faithfulness:{result.reflective_answer_faithfulness:.2f},"
        f"gold_fact_coverage:{result.reflective_gold_fact_coverage:.2f},"
        f"constraint_satisfaction:{result.reflective_constraint_satisfaction:.2f}"
    )
    print(f"auto_frontier_average_aqs_drop={result.auto_frontier_average_aqs_drop:.4f}")
    print(
        "auto_switch_counts="
        f"upgrade:{result.auto_audit.upgrade_count},"
        f"downgrade:{result.auto_audit.downgrade_count},"
        f"jump:{result.auto_audit.jump_count}"
    )
    print(f"fixed_lock_overrides={result.fixed_lock_override_count}/{result.fixed_lock_run_count}")
    print(f"I-1={'PASS' if result.i1_pass else 'FAIL'}")
    print(f"I-2={'PASS' if result.i2_pass else 'FAIL'}")
    print(f"I-3={'PASS' if result.i3_pass else 'FAIL'}")
    print(f"I-4={'PASS' if result.i4_pass else 'FAIL'}")
    print(f"I-5={'PASS' if result.i5_pass else 'FAIL'}")
    print(f"I-6={'PASS' if result.i6_pass else 'FAIL'}")
    print(f"I-7={'PASS' if result.i7_pass else 'FAIL'}")
    print(f"I-8={'PASS' if result.i8_pass else 'FAIL'}")
    print(f"phase_i_gate={'PASS' if result.access_gate_pass else 'FAIL'}")
    return 0


def cli_gate_main(argv: Sequence[str] | None = None) -> int:
    """Run the local Phase J unified CLI gate."""

    from .cli_gate import (
        assert_cli_gate,
        evaluate_cli_gate,
        write_cli_gate_report_json,
    )

    parser = argparse.ArgumentParser(
        prog="mindtest-phase-j-gate",
        description="Run the full local Phase J unified CLI gate.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/phase_j/gate_report.json",
        help="Output path for the persisted Phase J gate JSON report.",
    )
    parser.add_argument(
        "--dsn",
        help="Optional admin PostgreSQL DSN for demo/offline CLI flows.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = evaluate_cli_gate(postgres_admin_dsn=args.dsn)

    try:
        assert_cli_gate(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    output_path = write_cli_gate_report_json(args.output, result)
    print("Phase J gate report")
    print(f"report_path={output_path}")
    print(f"scenario_count={result.scenario_count}")
    print(f"help_coverage={result.help_coverage_count}/{result.help_total}")
    print(f"family_reachability={result.family_reachability_count}/{result.family_total}")
    print(
        "representative_flows="
        f"{result.representative_flow_pass_count}/{result.representative_flow_total}"
    )
    print(f"postgres_demo_configured={str(result.postgres_demo_configured).lower()}")
    print(f"config_audit={result.config_audit_pass_count}/{result.config_audit_total}")
    print(f"output_contracts={result.output_contract_pass_count}/{result.output_contract_total}")
    print(
        f"invalid_exit_contracts={result.invalid_exit_coverage_count}/{result.invalid_exit_total}"
    )
    print(
        "wrapped_regressions="
        f"{result.wrapped_regression_pass_count}/{result.wrapped_regression_total}"
    )
    print(f"J-1={'PASS' if result.j1_pass else 'FAIL'}")
    print(f"J-2={'PASS' if result.j2_pass else 'FAIL'}")
    print(f"J-3={'PASS' if result.j3_pass else 'FAIL'}")
    print(f"J-4={'PASS' if result.j4_pass else 'FAIL'}")
    print(f"J-5={'PASS' if result.j5_pass else 'FAIL'}")
    print(f"J-6={'PASS' if result.j6_pass else 'FAIL'}")
    print(f"phase_j_gate={'PASS' if result.cli_gate_pass else 'FAIL'}")
    return 0


def capability_gate_main(argv: Sequence[str] | None = None) -> int:
    """Run the local Phase K capability-layer gate."""

    parser = argparse.ArgumentParser(
        prog="mindtest-phase-k-gate",
        description="Run the local Phase K capability-layer gate.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/phase_k/gate_report.json",
        help="Output path for the persisted Phase K gate JSON report.",
    )
    parser.add_argument(
        "--live-provider",
        action="append",
        choices=_LIVE_CAPABILITY_PROVIDER_CHOICES,
        default=[],
        help=(
            "Optional live provider adapter to execute during the gate."
            " May be passed multiple times."
        ),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    adapters = _build_live_capability_adapters(args.live_provider)
    result = evaluate_capability_gate(adapters=adapters)

    try:
        assert_capability_gate(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    output_path = write_capability_gate_report_json(args.output, result)
    print("Phase K gate report")
    print(f"report_path={output_path}")
    print(f"live_providers={_format_live_provider_summary(adapters)}")
    print(
        "contracts="
        f"{result.contract_audit.request_contract_count}/{result.contract_audit.capability_count}"
    )
    print(
        "benchmark="
        f"{result.benchmark_result.passed_case_count}/{result.benchmark_result.case_count}"
    )
    audit = result.failure_audit
    print(
        "failure_audit="
        f"{audit.fallback_success_count + audit.structured_failure_count}"
        f"/{audit.audited_case_count}"
    )
    print(
        "trace_coverage="
        f"{result.trace_audit.complete_trace_count}/{result.trace_audit.audited_case_count}"
    )
    for provider_summary in result.compatibility_report.providers:
        print(
            f"provider_{provider_summary.provider_family.value}="
            f"pass_rate:{provider_summary.benchmark_pass_rate:.4f},"
            f"failed_cases:{provider_summary.benchmark_failed_case_count},"
            f"trace_coverage:{provider_summary.trace_coverage:.4f}"
        )
    print(f"K-1={'PASS' if result.k1_pass else 'FAIL'}")
    print(f"K-2={'PASS' if result.k2_pass else 'FAIL'}")
    print(f"K-3={'PASS' if result.k3_pass else 'FAIL'}")
    print(f"K-4={'PASS' if result.k4_pass else 'FAIL'}")
    print(f"K-5={'PASS' if result.k5_pass else 'FAIL'}")
    print(f"K-6={'PASS' if result.k6_pass else 'FAIL'}")
    print(f"K-7={'PASS' if result.k7_pass else 'FAIL'}")
    print(f"phase_k_gate={'PASS' if result.capability_gate_pass else 'FAIL'}")
    return 0


def capability_compatibility_report_main(argv: Sequence[str] | None = None) -> int:
    """Run the Phase K provider compatibility report."""

    parser = argparse.ArgumentParser(
        prog="mindtest-phase-k-compatibility-report",
        description="Run the Phase K provider compatibility report.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/phase_k/provider_compatibility.json",
        help="Output path for the persisted Phase K compatibility JSON report.",
    )
    parser.add_argument(
        "--live-provider",
        action="append",
        choices=_LIVE_CAPABILITY_PROVIDER_CHOICES,
        default=[],
        help=(
            "Optional live provider adapter to execute during the report."
            " May be passed multiple times."
        ),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    adapters = _build_live_capability_adapters(args.live_provider)
    report = evaluate_capability_provider_compatibility_report(adapters=adapters)
    output_path = write_capability_provider_compatibility_report_json(args.output, report)

    print("Phase K provider compatibility report")
    print(f"report_path={output_path}")
    print(f"live_providers={_format_live_provider_summary(adapters)}")
    print(f"benchmark_case_count={report.benchmark_case_count}")
    print(f"benchmark_pass_rate={report.benchmark_pass_rate:.4f}")
    print(f"failure_audit_pass_rate={report.failure_audit_pass_rate:.4f}")
    print(f"trace_audit_coverage={report.trace_audit_coverage:.4f}")
    for provider_summary in report.providers:
        print(
            f"provider_{provider_summary.provider_family.value}="
            f"benchmark_pass_rate:{provider_summary.benchmark_pass_rate:.4f},"
            f"failed_cases:{provider_summary.benchmark_failed_case_count},"
            f"trace_coverage:{provider_summary.trace_coverage:.4f}"
        )
    return 0


def product_transport_report_main(argv: Sequence[str] | None = None) -> int:
    """Run the product transport audit report."""

    parser = argparse.ArgumentParser(
        prog="mindtest-product-transport-report",
        description="Run the shared REST / MCP / product CLI transport audit report.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/product/transport_audit_report.json",
        help="Output path for the persisted product transport audit JSON report.",
    )
    parser.add_argument(
        "--markdown-output",
        default=None,
        help="Optional output path for a human-readable Markdown summary.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = evaluate_runtime_product_transport_audit_report()
    output_path = write_product_transport_audit_json(args.output, report)
    markdown_output_path = (
        write_product_transport_audit_markdown(
            args.markdown_output,
            report,
            title="Product Transport Audit Report",
        )
        if args.markdown_output
        else None
    )

    print("Product transport audit report")
    print(f"report_path={output_path}")
    if markdown_output_path is not None:
        print(f"markdown_path={markdown_output_path}")
    print(f"scenario_count={report.scenario_count}")
    print(f"coverage={report.coverage:.4f}")
    print(f"rest_mcp_pass_rate={report.rest_mcp_pass_rate:.4f}")
    print(f"rest_cli_pass_rate={report.rest_cli_pass_rate:.4f}")
    if report.failure_ids:
        print(f"failure_ids={','.join(report.failure_ids)}")
    print(f"product_transport_report={'PASS' if report.passed else 'FAIL'}")
    return 0


