"""CLI subcommands for demo scenarios and gate configuration."""

from __future__ import annotations

import argparse
import json
import os

from .access import AccessMode, AccessService, AccessTaskFamily
from .cli import (
    _LIVE_CAPABILITY_PROVIDER_CHOICES,
    _add_common_resolution_args,
    _open_isolated_demo_store,
    _parse_json_argument,
    _parse_text_or_json_value,
    _print_primitive_execution,
    _resolve_cli_config_from_args,
    _run_forwarded_command,
    _run_no_argv_command,
)
from .cli_config import CliBackend, ResolvedCliConfig, resolve_cli_config
from .cli_gates import (
    access_gate_main,
    capability_gate_main,
    cli_gate_main,
    governance_gate_main,
    kernel_gate_main,
    offline_gate_main,
    offline_startup_main,
    postgres_regression_main,
    primitive_gate_main,
    workspace_smoke_main,
)
from .cli_phase_gates import (
    benchmark_gate_main,
    frontend_gate_main,
    product_readiness_gate_main,
    strategy_gate_main,
)
from .fixtures.access_depth_bench import AccessDepthBenchCase, build_access_depth_bench_v1
from .fixtures.retrieval_benchmark import build_canonical_seed_objects
from .kernel.postgres_store import (
    PostgresMemoryStore,
    run_postgres_migrations,
    temporary_postgres_database,
)
from .kernel.schema import VALID_RECORD_KIND
from .offline import (
    OfflineJobKind,
    OfflineJobStatus,
    ReflectEpisodeJobPayload,
    new_offline_job,
)
from .primitives import Capability, PrimitiveExecutionContext
from .primitives.service import PrimitiveService


def _run_demo_ingest_read(args: argparse.Namespace) -> int:
    config = _resolve_cli_config_from_args(args)
    content = _parse_text_or_json_value(
        text_value=args.content,
        json_value=args.content_json,
        field_name="content",
    )
    write_context = PrimitiveExecutionContext(
        actor="mind-demo",
        budget_scope_id="mind-demo-ingest-read",
        budget_limit=None,
    )
    read_capabilities = [Capability.MEMORY_READ]
    if args.include_provenance:
        read_capabilities.append(Capability.MEMORY_READ_WITH_PROVENANCE)
    read_context = PrimitiveExecutionContext(
        actor="mind-demo",
        budget_scope_id="mind-demo-ingest-read",
        budget_limit=None,
        capabilities=read_capabilities,
    )

    with _open_isolated_demo_store(config, prefix="mind_demo_ingest_read") as store:
        service = PrimitiveService(store)
        write_result = service.write_raw(
            {
                "record_kind": args.record_kind,
                "content": content,
                "episode_id": args.episode_id,
                "timestamp_order": args.timestamp_order,
                **(
                    {
                        "direct_provenance": _parse_json_argument(
                            "provenance-json",
                            args.provenance_json,
                        )
                    }
                    if args.provenance_json
                    else {}
                ),
            },
            write_context,
        )
        if write_result.response is None:
            _print_primitive_execution(config, write_result)
            return 1
        object_id = str(write_result.response["object_id"])
        read_result = service.read(
            {
                "object_ids": [object_id],
                "include_provenance": args.include_provenance,
            },
            read_context,
        )

    print("Demo ingest-read")
    print(f"backend={config.backend.value}")
    print("storage_scope=isolated")
    print(f"write_outcome={write_result.outcome.value}")
    print(f"read_outcome={read_result.outcome.value}")
    print(f"object_id={object_id}")
    if write_result.response is not None:
        print(f"provenance_id={write_result.response.get('provenance_id', 'none')}")
    if read_result.response is not None:
        objects = read_result.response.get("objects", [])
        summaries = read_result.response.get("provenance_summaries", {})
        print(f"read_object_count={len(objects)}")
        print(f"provenance_summary_count={len(summaries)}")
        for index, obj in enumerate(objects, start=1):
            print(f"read_object_{index}={obj['id']}:{obj['type']}:{obj['status']}")
        print(
            "read_response_json="
            + json.dumps(
                read_result.response,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    return 0


def _demo_access_case(case_id: str | None) -> AccessDepthBenchCase:
    cases = build_access_depth_bench_v1()
    if case_id is not None:
        for case in cases:
            if case.case_id == case_id:
                return case
        raise SystemExit(f"Unknown access demo case_id '{case_id}'.")

    high_correctness_cases = [
        case for case in cases if case.task_family is AccessTaskFamily.HIGH_CORRECTNESS
    ]
    if high_correctness_cases:
        return high_correctness_cases[0]
    return cases[0]


def _run_demo_access_run(args: argparse.Namespace) -> int:
    config = _resolve_cli_config_from_args(args)
    case = _demo_access_case(args.case_id)
    requested_mode = args.mode or AccessMode.AUTO.value
    with _open_isolated_demo_store(config, prefix="mind_demo_access_run") as store:
        store.insert_objects(build_canonical_seed_objects())
        response = AccessService(store).run(
            {
                "requested_mode": requested_mode,
                "task_id": case.task_id,
                "task_family": case.task_family.value,
                "time_budget_ms": case.time_budget_ms,
                "hard_constraints": list(case.hard_constraints),
                "query": case.prompt,
                "filters": {"episode_id": case.episode_id},
            },
            PrimitiveExecutionContext(
                actor="mind-demo",
                budget_scope_id=f"mind-demo-access::{case.case_id}",
                budget_limit=None,
            ),
        )

    print("Demo access run")
    print(f"backend={config.backend.value}")
    print("storage_scope=isolated")
    print(f"case_id={case.case_id}")
    print(f"task_family={case.task_family.value}")
    print(f"recommended_mode={case.recommended_mode.value}")
    print(f"requested_mode={requested_mode}")
    print(f"resolved_mode={response.resolved_mode.value}")
    print(f"context_kind={response.context_kind.value}")
    print(f"context_object_count={len(response.context_object_ids)}")
    print(f"verification_note_count={len(response.verification_notes)}")
    print(f"trace_event_count={len(response.trace.events)}")
    for index, event in enumerate(response.trace.events, start=1):
        reason = event.reason_code.value if event.reason_code is not None else "none"
        switch = event.switch_kind.value if event.switch_kind is not None else "none"
        print(
            f"trace_{index}="
            f"{event.event_kind.value}:{event.mode.value}:{switch}:{reason}:{len(event.target_ids)}"
        )
    return 0


def _resolve_demo_postgres_config(args: argparse.Namespace) -> ResolvedCliConfig:
    backend = getattr(args, "backend", None) or (
        CliBackend.POSTGRESQL.value if getattr(args, "dsn", None) else None
    )
    return resolve_cli_config(
        profile=getattr(args, "profile", None),
        backend=backend,
        sqlite_path=getattr(args, "sqlite_path", None),
        postgres_dsn=getattr(args, "dsn", None),
        allow_sqlite=True,
    )


def _run_demo_offline_job(args: argparse.Namespace) -> int:
    config = _resolve_demo_postgres_config(args)
    if config.backend is not CliBackend.POSTGRESQL or config.postgres_dsn is None:
        raise SystemExit("demo offline-job requires --backend postgresql and a PostgreSQL DSN.")

    with temporary_postgres_database(config.postgres_dsn, prefix="mind_demo_offline_job") as dsn:
        run_postgres_migrations(dsn)
        job = new_offline_job(
            job_kind=OfflineJobKind.REFLECT_EPISODE,
            payload=ReflectEpisodeJobPayload(
                episode_id=args.episode_id,
                focus=args.focus,
            ),
            priority=args.priority,
            max_attempts=args.max_attempts,
        )
        with PostgresMemoryStore(dsn) as store:
            store.enqueue_offline_job(job)
            jobs = store.iter_offline_jobs(statuses=[OfflineJobStatus.PENDING])

    print("Demo offline job")
    print("backend=postgresql")
    print("storage_scope=isolated")
    print(f"job_id={job.job_id}")
    print(f"job_kind={job.job_kind.value}")
    print(f"pending_job_count={len(jobs)}")
    for index, queued_job in enumerate(jobs, start=1):
        print(
            f"job_{index}={queued_job.job_id}:{queued_job.job_kind.value}:{queued_job.status.value}"
        )
    return 0


def _configure_demo_commands(command_parser: argparse.ArgumentParser) -> None:
    demo_subparsers = command_parser.add_subparsers(
        dest="demo_command",
        metavar="demo-command",
    )

    ingest_read_parser = demo_subparsers.add_parser(
        "ingest-read",
        help="Run an isolated write_raw -> read demo flow.",
        description="Run an isolated write_raw -> read demo flow.",
    )
    _add_common_resolution_args(ingest_read_parser)
    ingest_read_parser.add_argument(
        "--record-kind",
        choices=sorted(VALID_RECORD_KIND),
        default="user_message",
        help="Raw record kind used by the demo.",
    )
    ingest_read_parser.add_argument(
        "--episode-id",
        default="episode-demo",
        help="Episode id used by the demo write_raw call.",
    )
    ingest_read_parser.add_argument(
        "--timestamp-order",
        type=int,
        default=1,
        help="Timestamp order used by the demo write_raw call.",
    )
    content_group = ingest_read_parser.add_mutually_exclusive_group()
    content_group.add_argument(
        "--content",
        default="remember this",
        help="Plain-text RawRecord content for the demo.",
    )
    content_group.add_argument(
        "--content-json",
        help="JSON RawRecord content payload for the demo.",
    )
    ingest_read_parser.add_argument(
        "--provenance-json",
        help="Optional JSON direct provenance payload for the demo write_raw call.",
    )
    ingest_read_parser.add_argument(
        "--include-provenance",
        action="store_true",
        help="Include runtime-safe provenance summaries in the demo read step.",
    )
    ingest_read_parser.set_defaults(_mind_handler=_run_demo_ingest_read)

    access_run_parser = demo_subparsers.add_parser(
        "access-run",
        help="Run an isolated runtime access demo flow on AccessDepthBench fixtures.",
        description="Run an isolated runtime access demo flow on AccessDepthBench fixtures.",
    )
    _add_common_resolution_args(access_run_parser)
    access_run_parser.add_argument(
        "--case-id",
        help="Optional AccessDepthBench case id. Defaults to the first high_correctness case.",
    )
    access_run_parser.add_argument(
        "--mode",
        choices=[mode.value for mode in AccessMode],
        help="Optional requested access mode. Defaults to auto.",
    )
    access_run_parser.set_defaults(_mind_handler=_run_demo_access_run)

    offline_job_parser = demo_subparsers.add_parser(
        "offline-job",
        help="Run an isolated PostgreSQL offline job enqueue demo.",
        description="Run an isolated PostgreSQL offline job enqueue demo.",
    )
    _add_common_resolution_args(offline_job_parser)
    offline_job_parser.add_argument(
        "--episode-id",
        default="episode-demo-offline",
        help="Episode id stored in the demo offline job payload.",
    )
    offline_job_parser.add_argument(
        "--focus",
        default="offline demo reflection",
        help="Focus string stored in the demo offline job payload.",
    )
    offline_job_parser.add_argument(
        "--priority",
        type=float,
        default=0.5,
        help="Priority used for the demo offline job.",
    )
    offline_job_parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Max attempts used for the demo offline job.",
    )
    offline_job_parser.set_defaults(_mind_handler=_run_demo_offline_job)


def _configure_gate_commands(command_parser: argparse.ArgumentParser) -> None:
    gate_subparsers = command_parser.add_subparsers(dest="gate_command", metavar="gate-command")

    kernel_parser = gate_subparsers.add_parser(
        "phase-b",
        help="Run the local Phase B formal gate.",
        description="Run the local Phase B formal gate.",
    )
    kernel_parser.set_defaults(_mind_handler=_run_no_argv_command(kernel_gate_main))

    primitive_parser = gate_subparsers.add_parser(
        "phase-c",
        help="Run the local Phase C formal gate.",
        description="Run the local Phase C formal gate.",
    )
    primitive_parser.set_defaults(_mind_handler=_run_no_argv_command(primitive_gate_main))

    workspace_parser = gate_subparsers.add_parser(
        "phase-d",
        help="Run the local Phase D smoke gate.",
        description="Run the local Phase D retrieval/workspace smoke gate.",
    )
    workspace_parser.set_defaults(_mind_handler=_run_no_argv_command(workspace_smoke_main))

    offline_startup_parser = gate_subparsers.add_parser(
        "phase-e-startup",
        help="Run the local Phase E startup baseline.",
        description="Run the local Phase E startup baseline.",
    )
    offline_startup_parser.set_defaults(_mind_handler=_run_no_argv_command(offline_startup_main))

    offline_parser = gate_subparsers.add_parser(
        "phase-e",
        help="Run the local Phase E formal gate.",
        description="Run the local Phase E formal gate.",
    )
    offline_parser.set_defaults(_mind_handler=_run_no_argv_command(offline_gate_main))

    phase_f_parser = gate_subparsers.add_parser(
        "phase-f",
        help="Run the local Phase F formal gate.",
        description="Run the full local Phase F formal gate.",
    )
    phase_f_parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="Independent run count for each system. Must be >= 3.",
    )
    phase_f_parser.add_argument(
        "--output",
        default="artifacts/phase_f/gate_report.json",
        help="Output path for the persisted Phase F gate JSON report.",
    )
    phase_f_parser.set_defaults(
        _mind_handler=_run_forwarded_command(
            benchmark_gate_main,
            (("repeat_count", "--repeat-count"), ("output", "--output")),
        )
    )

    phase_g_parser = gate_subparsers.add_parser(
        "phase-g",
        help="Run the local Phase G formal gate.",
        description="Run the full local Phase G strategy optimization gate.",
    )
    phase_g_parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="Independent run count for each system. Must be >= 3.",
    )
    phase_g_parser.add_argument(
        "--output",
        default="artifacts/phase_g/gate_report.json",
        help="Output path for the persisted Phase G gate JSON report.",
    )
    phase_g_parser.set_defaults(
        _mind_handler=_run_forwarded_command(
            strategy_gate_main,
            (("repeat_count", "--repeat-count"), ("output", "--output")),
        )
    )

    phase_h_parser = gate_subparsers.add_parser(
        "phase-h",
        help="Run the local Phase H formal gate.",
        description="Run the local Phase H provenance foundation gate.",
    )
    phase_h_parser.add_argument(
        "--output",
        default="artifacts/phase_h/gate_report.json",
        help="Output path for the persisted Phase H gate JSON report.",
    )
    phase_h_parser.set_defaults(
        _mind_handler=_run_forwarded_command(governance_gate_main, (("output", "--output"),))
    )

    phase_i_parser = gate_subparsers.add_parser(
        "phase-i",
        help="Run the local Phase I formal gate.",
        description="Run the local Phase I runtime access gate.",
    )
    phase_i_parser.add_argument(
        "--output",
        default="artifacts/phase_i/gate_report.json",
        help="Output path for the persisted Phase I gate JSON report.",
    )
    phase_i_parser.set_defaults(
        _mind_handler=_run_forwarded_command(access_gate_main, (("output", "--output"),))
    )

    phase_j_parser = gate_subparsers.add_parser(
        "phase-j",
        help="Run the local Phase J unified CLI gate.",
        description="Run the local Phase J unified CLI gate.",
    )
    phase_j_parser.add_argument(
        "--output",
        default="artifacts/phase_j/gate_report.json",
        help="Output path for the persisted Phase J gate JSON report.",
    )
    phase_j_parser.add_argument(
        "--dsn",
        default=os.environ.get("MIND_TEST_POSTGRES_DSN") or os.environ.get("MIND_POSTGRES_DSN"),
        help="Optional admin PostgreSQL DSN for demo/offline CLI flows.",
    )
    phase_j_parser.set_defaults(
        _mind_handler=_run_forwarded_command(
            cli_gate_main,
            (("output", "--output"), ("dsn", "--dsn")),
        )
    )

    phase_k_parser = gate_subparsers.add_parser(
        "phase-k",
        help="Run the local Phase K capability-layer gate.",
        description="Run the local Phase K capability-layer gate.",
    )
    phase_k_parser.add_argument(
        "--output",
        default="artifacts/phase_k/gate_report.json",
        help="Output path for the persisted Phase K gate JSON report.",
    )
    phase_k_parser.add_argument(
        "--live-provider",
        action="append",
        choices=_LIVE_CAPABILITY_PROVIDER_CHOICES,
        default=[],
        help=(
            "Optional live provider adapter to execute during the gate."
            " May be passed multiple times."
        ),
    )
    phase_k_parser.set_defaults(
        _mind_handler=_run_forwarded_command(
            capability_gate_main,
            (("output", "--output"), ("live_provider", "--live-provider")),
        )
    )

    phase_m_parser = gate_subparsers.add_parser(
        "phase-m",
        help="Run the local Phase M frontend-experience gate.",
        description="Run the local Phase M frontend-experience gate.",
    )
    phase_m_parser.add_argument(
        "--output",
        default="artifacts/phase_m/gate_report.json",
        help="Output path for the persisted Phase M gate JSON report.",
    )
    phase_m_parser.set_defaults(
        _mind_handler=_run_forwarded_command(
            frontend_gate_main,
            (("output", "--output"),),
        )
    )

    product_readiness_parser = gate_subparsers.add_parser(
        "product-readiness",
        help="Run the aggregated product readiness gate.",
        description="Run the aggregated product readiness gate.",
    )
    product_readiness_parser.add_argument(
        "--output",
        default="artifacts/product/product_readiness_gate.json",
        help="Output path for the persisted product readiness gate JSON report.",
    )
    product_readiness_parser.add_argument(
        "--markdown-output",
        default=None,
        help="Optional output path for a human-readable Markdown gate summary.",
    )
    product_readiness_parser.set_defaults(
        _mind_handler=_run_forwarded_command(
            product_readiness_gate_main,
            (("output", "--output"), ("markdown_output", "--markdown-output")),
        )
    )

    postgres_regression_parser = gate_subparsers.add_parser(
        "postgres-regression",
        help="Run the PostgreSQL regression bundle for Phase B/C/D/E.",
        description="Run Phase B/C/D/E regressions against a migrated PostgreSQL database.",
    )
    postgres_regression_parser.add_argument(
        "--dsn",
        default=os.environ.get("MIND_POSTGRES_DSN"),
        help="Admin PostgreSQL DSN. Falls back to MIND_POSTGRES_DSN.",
    )
    postgres_regression_parser.set_defaults(
        _mind_handler=_run_forwarded_command(
            postgres_regression_main,
            (("dsn", "--dsn"),),
        )
    )


