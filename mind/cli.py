"""Project CLI entry points."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .access import (
    AccessMode,
    AccessService,
    AccessTaskFamily,
    assert_access_gate,
    evaluate_access_benchmark,
    evaluate_access_gate,
    write_access_gate_report_json,
)
from .cli_config import (
    CliBackend,
    CliProfile,
    ResolvedCliConfig,
    build_config_doctor_checks,
    list_cli_profiles,
    redact_dsn,
    resolve_cli_config,
)
from .eval import (
    FixedSummaryMemoryBaselineSystem,
    LongHorizonBenchmarkRunner,
    MindLongHorizonSystem,
    NoMemoryBaselineSystem,
    OptimizedMindStrategy,
    PlainRagBaselineSystem,
    assert_benchmark_comparison,
    assert_benchmark_gate,
    assert_strategy_gate,
    build_benchmark_suite_report,
    evaluate_benchmark_comparison,
    evaluate_benchmark_gate,
    evaluate_fixed_rule_cost_report,
    evaluate_strategy_gate,
    write_benchmark_comparison_report_json,
    write_benchmark_gate_report_json,
    write_benchmark_suite_report_json,
    write_strategy_cost_report_json,
    write_strategy_gate_report_json,
)
from .fixtures.access_depth_bench import AccessDepthBenchCase, build_access_depth_bench_v1
from .fixtures.long_horizon_eval import (
    build_long_horizon_eval_manifest_v1,
    build_long_horizon_eval_v1,
)
from .fixtures.retrieval_benchmark import build_canonical_seed_objects
from .governance import (
    GovernanceService,
    GovernanceServiceError,
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
from .kernel.provenance import ProducerKind
from .kernel.schema import VALID_RECORD_KIND
from .kernel.store import SQLiteMemoryStore
from .offline import (
    OfflineJobKind,
    OfflineJobStatus,
    OfflineMaintenanceService,
    OfflineWorker,
    PromoteSchemaJobPayload,
    ReflectEpisodeJobPayload,
    assert_offline_gate,
    assert_offline_startup,
    evaluate_offline_gate,
    evaluate_offline_startup,
    new_offline_job,
    select_replay_targets,
)
from .primitives import Capability, PrimitiveExecutionContext, PrimitiveName, PrimitiveOutcome
from .primitives.gate import assert_primitive_gate, evaluate_primitive_gate
from .primitives.service import PrimitiveService
from .workspace import assert_workspace_smoke, evaluate_workspace_smoke


@dataclass(frozen=True)
class _MindCommandGroup:
    name: str
    help: str
    description: str
    examples: tuple[str, ...]


_ZeroArgMain = Callable[[], int]
_ArgvMain = Callable[[Sequence[str] | None], int]
_CliHandler = Callable[[argparse.Namespace], int]
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SUMMARY_SCOPES: tuple[str, ...] = ("episode", "task", "object_set")
_ACCESS_QUERY_MODES: tuple[str, ...] = ("keyword", "time_window", "vector")
_ACCEPTANCE_REPORTS: dict[str, Path] = {
    phase: _REPO_ROOT / f"docs/reports/phase_{phase}_acceptance_report.md"
    for phase in ("a", "b", "c", "d", "e", "f", "g", "h", "i", "j")
}


_MIND_COMMAND_GROUPS: tuple[_MindCommandGroup, ...] = (
    _MindCommandGroup(
        name="primitive",
        help="Inspect and operate the core memory primitives.",
        description=(
            "Primitive memory operations such as write_raw, read, retrieve, summarize, "
            "reflect, link, and lightweight reorganization."
        ),
        examples=(
            "mindtest primitive write-raw --help",
            "mindtest primitive read --help",
            "mindtest primitive retrieve --help",
            "mindtest primitive summarize --help",
        ),
    ),
    _MindCommandGroup(
        name="access",
        help="Run runtime access modes and access evaluation flows.",
        description=(
            "Runtime access entry points for flash / recall / reconstruct / reflective "
            "access and related benchmark flows."
        ),
        examples=(
            "mindtest access run --mode flash --help",
            "mindtest access run --mode auto --help",
            "mindtest access benchmark --help",
        ),
    ),
    _MindCommandGroup(
        name="offline",
        help="Drive offline maintenance workers and replay workflows.",
        description=(
            "Offline maintenance commands for worker batches, replay targets, episode "
            "reflection, and future maintenance jobs."
        ),
        examples=(
            "mindtest offline worker --help",
            "mindtest offline replay --help",
            "mindtest offline reflect-episode --help",
        ),
    ),
    _MindCommandGroup(
        name="governance",
        help="Plan, preview, and execute governance workflows.",
        description=(
            "Governance control-plane commands for provenance-aware plan / preview / "
            "execute flows and future reshape operations."
        ),
        examples=(
            "mindtest governance plan-conceal --help",
            "mindtest governance preview --help",
            "mindtest governance execute-conceal --help",
        ),
    ),
    _MindCommandGroup(
        name="gate",
        help="Run local gates, audits, and regression entry points.",
        description=(
            "Formal gate commands for phase-local validation, PostgreSQL regression, "
            "and future unified gate execution."
        ),
        examples=(
            "mindtest gate phase-b --help",
            "mindtest gate phase-i --help",
            "mindtest gate postgres-regression --help",
        ),
    ),
    _MindCommandGroup(
        name="report",
        help="Generate or inspect benchmark and acceptance reports.",
        description=(
            "Report-oriented commands for benchmark outputs, acceptance reports, and "
            "future report collection helpers."
        ),
        examples=(
            "mindtest report phase-f-ci --help",
            "mindtest report phase-g-cost --help",
            "mindtest report acceptance --phase h",
        ),
    ),
    _MindCommandGroup(
        name="demo",
        help="Run guided demos for the main memory capabilities.",
        description=(
            "Demo flows that package the main memory capabilities into guided ingest, "
            "retrieve, access, offline, and gate walkthroughs."
        ),
        examples=(
            "mindtest demo ingest-read --help",
            "mindtest demo access-run --help",
            "mindtest demo offline-job --help",
        ),
    ),
    _MindCommandGroup(
        name="config",
        help="Inspect CLI profiles, backends, and environment config.",
        description=(
            "Configuration entry points for profiles, backend selection, runtime "
            "environment checks, and future provider settings."
        ),
        examples=(
            "mindtest config show --help",
            "mindtest config profile --help",
            "mindtest config doctor --help",
        ),
    ),
)


def _format_examples(examples: Sequence[str]) -> str:
    return "Examples:\n" + "\n".join(f"  {example}" for example in examples)


def _command_group_lookup() -> dict[str, _MindCommandGroup]:
    return {group.name: group for group in _MIND_COMMAND_GROUPS}


def _print_bound_help(args: argparse.Namespace) -> int:
    parser = getattr(args, "_mind_parser", None)
    if parser is None:
        raise SystemExit("internal CLI error: missing bound parser")
    parser.print_help()
    return 0


def _run_no_argv_command(main_fn: _ZeroArgMain) -> _CliHandler:
    def handler(_: argparse.Namespace) -> int:
        return main_fn()

    return handler


def _build_forwarded_argv(
    args: argparse.Namespace,
    option_pairs: Sequence[tuple[str, str]],
) -> list[str]:
    forwarded: list[str] = []
    for attr_name, flag in option_pairs:
        value = getattr(args, attr_name)
        if value is None:
            continue
        forwarded.extend((flag, str(value)))
    return forwarded


def _run_forwarded_command(
    main_fn: _ArgvMain,
    option_pairs: Sequence[tuple[str, str]],
) -> _CliHandler:
    def handler(args: argparse.Namespace) -> int:
        return main_fn(_build_forwarded_argv(args, option_pairs))

    return handler


def _add_common_resolution_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile",
        choices=[profile.value for profile in CliProfile],
        help="CLI profile preset used as the base resolution input.",
    )
    parser.add_argument(
        "--backend",
        choices=[backend.value for backend in CliBackend],
        help="Optional backend override for the active command.",
    )
    parser.add_argument(
        "--sqlite-path",
        help="Optional SQLite path override for the sqlite backend.",
    )
    parser.add_argument(
        "--dsn",
        help="Optional PostgreSQL DSN override for the postgresql backend.",
    )


def _add_common_primitive_context_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--actor",
        default="mind-cli",
        help="Actor id stamped onto primitive logs and provenance fallback records.",
    )
    parser.add_argument(
        "--budget-scope-id",
        default="mind-cli",
        help="Budget scope id used for primitive cost accounting.",
    )
    parser.add_argument(
        "--budget-limit",
        type=float,
        help="Optional global budget limit enforced by the primitive runtime.",
    )
    parser.add_argument(
        "--capability",
        action="append",
        choices=[capability.value for capability in Capability],
        default=[],
        help="Optional extra capability. May be passed multiple times.",
    )


@contextmanager
def _open_cli_store(config: ResolvedCliConfig) -> Iterator[SQLiteMemoryStore | PostgresMemoryStore]:
    if config.backend is CliBackend.SQLITE:
        assert config.sqlite_path is not None
        with SQLiteMemoryStore(config.sqlite_path) as store:
            yield store
        return

    if config.postgres_dsn is None:
        raise SystemExit("Resolved PostgreSQL backend requires --dsn or a matching env var.")

    run_postgres_migrations(config.postgres_dsn)
    with PostgresMemoryStore(config.postgres_dsn) as store:
        yield store


@contextmanager
def _open_isolated_demo_store(
    config: ResolvedCliConfig,
    *,
    prefix: str,
) -> Iterator[SQLiteMemoryStore | PostgresMemoryStore]:
    if config.backend is CliBackend.SQLITE:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / f"{prefix}.sqlite3"
            with SQLiteMemoryStore(path) as store:
                yield store
        return

    if config.postgres_dsn is None:
        raise SystemExit("Resolved PostgreSQL backend requires --dsn or a matching env var.")

    with temporary_postgres_database(config.postgres_dsn, prefix=prefix) as database_dsn:
        run_postgres_migrations(database_dsn)
        with PostgresMemoryStore(database_dsn) as store:
            yield store


def _build_primitive_context(
    args: argparse.Namespace,
    *,
    required_capabilities: Sequence[Capability] = (),
) -> PrimitiveExecutionContext:
    capabilities: list[Capability] = [Capability.MEMORY_READ]
    for capability_name in getattr(args, "capability", []):
        capability = Capability(capability_name)
        if capability not in capabilities:
            capabilities.append(capability)
    for capability in required_capabilities:
        if capability not in capabilities:
            capabilities.append(capability)
    return PrimitiveExecutionContext(
        actor=args.actor,
        budget_scope_id=args.budget_scope_id,
        budget_limit=args.budget_limit,
        capabilities=capabilities,
    )


def _parse_json_argument(flag_name: str, payload: str) -> Any:
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--{flag_name} must be valid JSON: {exc.msg}.") from exc


def _parse_text_or_json_value(
    *,
    text_value: str | None,
    json_value: str | None,
    field_name: str,
) -> Any:
    if text_value is not None and json_value is not None:
        raise SystemExit(f"Provide only one text or JSON value for {field_name}.")
    if json_value is not None:
        return _parse_json_argument(f"{field_name}-json", json_value)
    if text_value is not None:
        return text_value
    raise SystemExit(f"Missing required {field_name} value.")


def _execute_primitive(
    args: argparse.Namespace,
    *,
    method_name: str,
    request_payload: dict[str, Any],
    required_capabilities: Sequence[Capability] = (),
) -> int:
    config = _resolve_cli_config_from_args(args)
    context = _build_primitive_context(args, required_capabilities=required_capabilities)
    with _open_cli_store(config) as store:
        service = PrimitiveService(store)
        method = getattr(service, method_name)
        result = method(request_payload, context)
    _print_primitive_execution(config, result)
    return 0 if result.outcome is PrimitiveOutcome.SUCCESS else 1


def _print_primitive_execution(config: ResolvedCliConfig, result: Any) -> None:
    print("Primitive execution")
    print(f"primitive={result.primitive.value}")
    print(f"outcome={result.outcome.value}")
    print(f"backend={config.backend.value}")
    if config.sqlite_path is not None:
        print(f"sqlite_path={config.sqlite_path.as_posix()}")
    if config.postgres_dsn is not None:
        print(f"postgres_dsn={redact_dsn(config.postgres_dsn)}")
    print(f"target_count={len(result.target_ids)}")
    for index, target_id in enumerate(result.target_ids, start=1):
        print(f"target_{index}={target_id}")
    cost_total = sum(cost.amount for cost in result.cost)
    print(f"cost_total={cost_total:.2f}")

    if result.response is not None:
        for line in _primitive_response_lines(result.primitive, result.response):
            print(line)
        print(
            "response_json="
            + json.dumps(result.response, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        )
        return

    assert result.error is not None
    print(f"error_code={result.error.code.value}")
    print(f"error_message={result.error.message}")
    if result.error.details:
        print(
            "error_details_json="
            + json.dumps(
                result.error.details,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
        )


def _primitive_response_lines(primitive: PrimitiveName, response: dict[str, Any]) -> list[str]:
    if primitive is PrimitiveName.WRITE_RAW:
        return [
            f"object_id={response['object_id']}",
            f"version={response['version']}",
            f"provenance_id={response.get('provenance_id', 'none')}",
        ]
    if primitive is PrimitiveName.READ:
        objects = response.get("objects", [])
        summaries = response.get("provenance_summaries", {})
        lines = [
            f"object_count={len(objects)}",
            f"provenance_summary_count={len(summaries)}",
        ]
        for index, obj in enumerate(objects, start=1):
            lines.append(f"object_{index}={obj['id']}:{obj['type']}:{obj['status']}")
        return lines
    if primitive is PrimitiveName.RETRIEVE:
        candidate_ids = response.get("candidate_ids", [])
        scores = response.get("scores", [])
        evidence_summary = response.get("evidence_summary", {})
        lines = [
            f"candidate_count={len(candidate_ids)}",
            "evidence_summary_json="
            + json.dumps(
                evidence_summary,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ]
        for index, candidate_id in enumerate(candidate_ids, start=1):
            score = scores[index - 1]
            lines.append(f"candidate_{index}={candidate_id}:{score:.4f}")
        return lines
    if primitive is PrimitiveName.SUMMARIZE:
        return [f"summary_object_id={response['summary_object_id']}"]
    if primitive is PrimitiveName.LINK:
        return [f"link_object_id={response['link_object_id']}"]
    if primitive is PrimitiveName.REFLECT:
        return [f"reflection_object_id={response['reflection_object_id']}"]
    if primitive is PrimitiveName.REORGANIZE_SIMPLE:
        updated_ids = response.get("updated_ids", [])
        new_object_ids = response.get("new_object_ids", [])
        lines = [
            f"updated_count={len(updated_ids)}",
            f"new_object_count={len(new_object_ids)}",
        ]
        for index, object_id in enumerate(updated_ids, start=1):
            lines.append(f"updated_{index}={object_id}")
        for index, object_id in enumerate(new_object_ids, start=1):
            lines.append(f"new_object_{index}={object_id}")
        return lines
    return []


def _run_primitive_write_raw(args: argparse.Namespace) -> int:
    content = _parse_text_or_json_value(
        text_value=args.content,
        json_value=args.content_json,
        field_name="content",
    )
    request_payload: dict[str, Any] = {
        "record_kind": args.record_kind,
        "content": content,
        "episode_id": args.episode_id,
        "timestamp_order": args.timestamp_order,
    }
    if args.provenance_json:
        request_payload["direct_provenance"] = _parse_json_argument(
            "provenance-json",
            args.provenance_json,
        )
    return _execute_primitive(args, method_name="write_raw", request_payload=request_payload)


def _run_primitive_read(args: argparse.Namespace) -> int:
    required_capabilities = (
        (Capability.MEMORY_READ_WITH_PROVENANCE,) if args.include_provenance else ()
    )
    return _execute_primitive(
        args,
        method_name="read",
        request_payload={
            "object_ids": list(args.object_id),
            "include_provenance": args.include_provenance,
        },
        required_capabilities=required_capabilities,
    )


def _run_primitive_retrieve(args: argparse.Namespace) -> int:
    query = _parse_text_or_json_value(
        text_value=args.query,
        json_value=args.query_json,
        field_name="query",
    )
    query_modes = list(dict.fromkeys(args.query_mode))
    if not query_modes:
        query_modes = ["keyword"]
    request_payload = {
        "query": query,
        "query_modes": query_modes,
        "budget": {
            "max_candidates": args.max_candidates,
            **({"max_cost": args.max_cost} if args.max_cost is not None else {}),
        },
        "filters": {
            "episode_id": args.episode_id,
            "task_id": args.task_id,
            "object_types": list(args.object_type),
            "statuses": list(args.status),
        },
    }
    return _execute_primitive(args, method_name="retrieve", request_payload=request_payload)


def _run_primitive_summarize(args: argparse.Namespace) -> int:
    return _execute_primitive(
        args,
        method_name="summarize",
        request_payload={
            "input_refs": list(args.input_ref),
            "summary_scope": args.summary_scope,
            "target_kind": args.target_kind,
        },
    )


def _run_primitive_link(args: argparse.Namespace) -> int:
    return _execute_primitive(
        args,
        method_name="link",
        request_payload={
            "src_id": args.src_id,
            "dst_id": args.dst_id,
            "relation_type": args.relation_type,
            "evidence_refs": list(args.evidence_ref),
        },
    )


def _run_primitive_reflect(args: argparse.Namespace) -> int:
    focus = _parse_text_or_json_value(
        text_value=args.focus,
        json_value=args.focus_json,
        field_name="focus",
    )
    return _execute_primitive(
        args,
        method_name="reflect",
        request_payload={
            "episode_id": args.episode_id,
            "focus": focus,
        },
    )


def _run_primitive_reorganize_simple(args: argparse.Namespace) -> int:
    return _execute_primitive(
        args,
        method_name="reorganize_simple",
        request_payload={
            "target_refs": list(args.target_ref),
            "operation": args.operation,
            "reason": args.reason,
        },
    )


def _configure_primitive_commands(command_parser: argparse.ArgumentParser) -> None:
    primitive_subparsers = command_parser.add_subparsers(
        dest="primitive_command",
        metavar="primitive-command",
    )

    write_raw_parser = primitive_subparsers.add_parser(
        "write-raw",
        help="Write one RawRecord through the typed primitive contract.",
        description="Write one RawRecord through the typed primitive contract.",
    )
    _add_common_resolution_args(write_raw_parser)
    _add_common_primitive_context_args(write_raw_parser)
    write_raw_parser.add_argument(
        "--record-kind",
        choices=sorted(VALID_RECORD_KIND),
        required=True,
        help="Raw record kind.",
    )
    write_raw_parser.add_argument("--episode-id", required=True, help="Bound episode id.")
    write_raw_parser.add_argument(
        "--timestamp-order",
        type=int,
        required=True,
        help="Monotonic timestamp order within the episode.",
    )
    content_group = write_raw_parser.add_mutually_exclusive_group(required=True)
    content_group.add_argument("--content", help="Plain-text RawRecord content.")
    content_group.add_argument("--content-json", help="JSON RawRecord content payload.")
    write_raw_parser.add_argument(
        "--provenance-json",
        help="Optional JSON direct provenance payload bound to this raw record.",
    )
    write_raw_parser.set_defaults(_mind_handler=_run_primitive_write_raw)

    read_parser = primitive_subparsers.add_parser(
        "read",
        help="Read one or more memory objects by id.",
        description="Read one or more memory objects by id.",
    )
    _add_common_resolution_args(read_parser)
    _add_common_primitive_context_args(read_parser)
    read_parser.add_argument(
        "--object-id",
        action="append",
        required=True,
        default=[],
        help="Object id to read. May be passed multiple times.",
    )
    read_parser.add_argument(
        "--include-provenance",
        action="store_true",
        help="Include runtime-safe provenance summaries for raw objects.",
    )
    read_parser.set_defaults(_mind_handler=_run_primitive_read)

    retrieve_parser = primitive_subparsers.add_parser(
        "retrieve",
        help="Retrieve candidate memory objects for a query.",
        description="Retrieve candidate memory objects for a query.",
    )
    _add_common_resolution_args(retrieve_parser)
    _add_common_primitive_context_args(retrieve_parser)
    query_group = retrieve_parser.add_mutually_exclusive_group(required=True)
    query_group.add_argument("--query", help="Plain-text retrieval query.")
    query_group.add_argument("--query-json", help="JSON retrieval query payload.")
    retrieve_parser.add_argument(
        "--query-mode",
        action="append",
        choices=["keyword", "time_window", "vector"],
        default=[],
        help="Retrieval query mode. May be passed multiple times.",
    )
    retrieve_parser.add_argument(
        "--max-candidates",
        type=int,
        default=5,
        help="Maximum candidate count requested from the primitive contract.",
    )
    retrieve_parser.add_argument(
        "--max-cost",
        type=float,
        help="Optional request-scoped budget ceiling.",
    )
    retrieve_parser.add_argument(
        "--object-type",
        action="append",
        default=[],
        help="Optional object type filter. May be passed multiple times.",
    )
    retrieve_parser.add_argument(
        "--status",
        action="append",
        default=[],
        help="Optional status filter. May be passed multiple times.",
    )
    retrieve_parser.add_argument("--episode-id", help="Optional episode filter.")
    retrieve_parser.add_argument("--task-id", help="Optional task filter.")
    retrieve_parser.set_defaults(_mind_handler=_run_primitive_retrieve)

    summarize_parser = primitive_subparsers.add_parser(
        "summarize",
        help="Create one SummaryNote from existing refs.",
        description="Create one SummaryNote from existing refs.",
    )
    _add_common_resolution_args(summarize_parser)
    _add_common_primitive_context_args(summarize_parser)
    summarize_parser.add_argument(
        "--input-ref",
        action="append",
        required=True,
        default=[],
        help="Input object id. May be passed multiple times.",
    )
    summarize_parser.add_argument(
        "--summary-scope",
        choices=_SUMMARY_SCOPES,
        required=True,
        help="Summary scope frozen by the primitive contract.",
    )
    summarize_parser.add_argument("--target-kind", required=True, help="Target semantic kind.")
    summarize_parser.set_defaults(_mind_handler=_run_primitive_summarize)

    link_parser = primitive_subparsers.add_parser(
        "link",
        help="Create one LinkEdge from existing refs.",
        description="Create one LinkEdge from existing refs.",
    )
    _add_common_resolution_args(link_parser)
    _add_common_primitive_context_args(link_parser)
    link_parser.add_argument("--src-id", required=True, help="Source object id.")
    link_parser.add_argument("--dst-id", required=True, help="Destination object id.")
    link_parser.add_argument("--relation-type", required=True, help="Relation label.")
    link_parser.add_argument(
        "--evidence-ref",
        action="append",
        required=True,
        default=[],
        help="Evidence object id. May be passed multiple times.",
    )
    link_parser.set_defaults(_mind_handler=_run_primitive_link)

    reflect_parser = primitive_subparsers.add_parser(
        "reflect",
        help="Create one ReflectionNote for an episode.",
        description="Create one ReflectionNote for an episode.",
    )
    _add_common_resolution_args(reflect_parser)
    _add_common_primitive_context_args(reflect_parser)
    reflect_parser.add_argument("--episode-id", required=True, help="Target episode id.")
    focus_group = reflect_parser.add_mutually_exclusive_group(required=True)
    focus_group.add_argument("--focus", help="Plain-text reflection focus.")
    focus_group.add_argument("--focus-json", help="JSON reflection focus payload.")
    reflect_parser.set_defaults(_mind_handler=_run_primitive_reflect)

    reorganize_parser = primitive_subparsers.add_parser(
        "reorganize-simple",
        help="Run the lightweight reorganize_simple primitive.",
        description="Run the lightweight reorganize_simple primitive.",
    )
    _add_common_resolution_args(reorganize_parser)
    _add_common_primitive_context_args(reorganize_parser)
    reorganize_parser.add_argument(
        "--target-ref",
        action="append",
        required=True,
        default=[],
        help="Target object id. May be passed multiple times.",
    )
    reorganize_parser.add_argument(
        "--operation",
        choices=["archive", "deprecate", "reprioritize", "synthesize_schema"],
        required=True,
        help="Lightweight reorganize operation.",
    )
    reorganize_parser.add_argument("--reason", required=True, help="Human-readable reason.")
    reorganize_parser.set_defaults(_mind_handler=_run_primitive_reorganize_simple)


def _run_access(args: argparse.Namespace) -> int:
    config = _resolve_cli_config_from_args(args)
    context = _build_primitive_context(args)
    query_modes = list(dict.fromkeys(args.query_mode))
    if not query_modes:
        query_modes = ["keyword"]

    request_payload = {
        "requested_mode": args.mode,
        "task_id": args.task_id,
        "query": _parse_text_or_json_value(
            text_value=args.query,
            json_value=args.query_json,
            field_name="query",
        ),
        "query_modes": query_modes,
        "filters": {
            "episode_id": args.episode_id,
            "task_id": args.filter_task_id,
            "object_types": list(args.object_type),
            "statuses": list(args.status),
        },
        "hard_constraints": list(args.hard_constraint),
    }
    if args.task_family is not None:
        request_payload["task_family"] = args.task_family
    if args.time_budget_ms is not None:
        request_payload["time_budget_ms"] = args.time_budget_ms

    seeded_fixture_count = 0
    with _open_cli_store(config) as store:
        if args.seed_bench_fixtures:
            seeded_fixture_count = _seed_canonical_objects_if_empty(store)
        response = AccessService(store).run(request_payload, context)

    _print_access_run(
        config,
        response,
        requested_mode=args.mode,
        seeded_fixture_count=seeded_fixture_count,
    )
    return 0


def _run_access_benchmark(args: argparse.Namespace) -> int:
    config = _resolve_cli_config_from_args(args)
    if config.backend is CliBackend.SQLITE:
        result = evaluate_access_benchmark()
    else:
        if config.postgres_dsn is None:
            raise SystemExit("Resolved PostgreSQL backend requires --dsn or a matching env var.")
        with temporary_postgres_database(
            config.postgres_dsn,
            prefix="mind_access_benchmark",
        ) as database_dsn:
            run_postgres_migrations(database_dsn)
            result = evaluate_access_benchmark(
                Path("mind_access_benchmark.sqlite3"),
                build_postgres_store_factory(database_dsn),
            )

    _print_access_benchmark(config, result)
    return 0


def _seed_canonical_objects_if_empty(
    store: SQLiteMemoryStore | PostgresMemoryStore,
) -> int:
    if store.iter_objects():
        return 0
    objects = build_canonical_seed_objects()
    store.insert_objects(objects)
    return len(objects)


def _print_access_run(
    config: ResolvedCliConfig,
    response: Any,
    *,
    requested_mode: str,
    seeded_fixture_count: int,
) -> None:
    print("Access run")
    print(f"requested_mode={requested_mode}")
    print(f"resolved_mode={response.resolved_mode.value}")
    print(f"context_kind={response.context_kind.value}")
    print(f"backend={config.backend.value}")
    print(f"seeded_fixture_count={seeded_fixture_count}")
    if config.sqlite_path is not None:
        print(f"sqlite_path={config.sqlite_path.as_posix()}")
    if config.postgres_dsn is not None:
        print(f"postgres_dsn={redact_dsn(config.postgres_dsn)}")
    print(f"context_object_count={len(response.context_object_ids)}")
    print(f"context_token_count={response.context_token_count}")
    print(f"candidate_count={len(response.candidate_ids)}")
    print(f"read_count={len(response.read_object_ids)}")
    print(f"expanded_count={len(response.expanded_object_ids)}")
    print(f"selected_count={len(response.selected_object_ids)}")
    print(f"verification_note_count={len(response.verification_notes)}")
    print(f"trace_event_count={len(response.trace.events)}")
    for index, object_id in enumerate(response.context_object_ids, start=1):
        print(f"context_object_{index}={object_id}")
    for index, object_id in enumerate(response.selected_object_ids, start=1):
        print(f"selected_object_{index}={object_id}")
    for index, note in enumerate(response.verification_notes, start=1):
        print(f"verification_note_{index}={note}")
    for index, event in enumerate(response.trace.events, start=1):
        reason = event.reason_code.value if event.reason_code is not None else "none"
        switch = event.switch_kind.value if event.switch_kind is not None else "none"
        print(
            f"trace_{index}="
            f"{event.event_kind.value}:{event.mode.value}:{switch}:{reason}:{len(event.target_ids)}"
        )


def _print_access_benchmark(config: ResolvedCliConfig, result: Any) -> None:
    print("Access benchmark")
    print(f"backend={config.backend.value}")
    print("storage_scope=isolated")
    print(f"case_count={result.case_count}")
    print(f"run_count={result.run_count}")
    print(f"aggregate_count={len(result.mode_family_aggregates)}")
    print(f"frontier_count={len(result.frontier_comparisons)}")
    for index, comparison in enumerate(result.frontier_comparisons, start=1):
        print(
            f"frontier_{index}="
            f"{comparison.task_family.value}:{comparison.family_best_fixed_mode.value}:"
            f"{comparison.auto_aqs:.4f}:{comparison.auto_cost_efficiency_score:.4f}:"
            f"{comparison.auto_aqs_drop:.4f}"
        )
    for index, aggregate in enumerate(result.mode_family_aggregates, start=1):
        print(
            f"aggregate_{index}="
            f"{aggregate.requested_mode.value}:{aggregate.task_family.value}:"
            f"{aggregate.answer_quality_score:.4f}:{aggregate.cost_efficiency_score:.4f}:"
            f"{aggregate.time_budget_hit_rate:.4f}"
        )


def _configure_access_commands(command_parser: argparse.ArgumentParser) -> None:
    access_subparsers = command_parser.add_subparsers(
        dest="access_command",
        metavar="access-command",
    )

    run_parser = access_subparsers.add_parser(
        "run",
        help="Run one fixed or auto runtime access execution.",
        description="Run one fixed or auto runtime access execution.",
    )
    _add_common_resolution_args(run_parser)
    _add_common_primitive_context_args(run_parser)
    run_parser.add_argument(
        "--mode",
        choices=[mode.value for mode in AccessMode],
        required=True,
        help="Requested runtime access mode.",
    )
    run_parser.add_argument("--task-id", required=True, help="Task id passed into the access run.")
    query_group = run_parser.add_mutually_exclusive_group(required=True)
    query_group.add_argument("--query", help="Plain-text access query.")
    query_group.add_argument("--query-json", help="JSON access query payload.")
    run_parser.add_argument(
        "--task-family",
        choices=[family.value for family in AccessTaskFamily],
        help="Optional access task family for auto scheduling.",
    )
    run_parser.add_argument(
        "--time-budget-ms",
        type=int,
        help="Optional time budget for access-mode planning.",
    )
    run_parser.add_argument(
        "--hard-constraint",
        action="append",
        default=[],
        help="Optional hard constraint. May be passed multiple times.",
    )
    run_parser.add_argument(
        "--query-mode",
        action="append",
        choices=_ACCESS_QUERY_MODES,
        default=[],
        help="Retrieval query mode. May be passed multiple times.",
    )
    run_parser.add_argument("--episode-id", help="Optional episode filter.")
    run_parser.add_argument(
        "--filter-task-id",
        help="Optional retrieval-layer task filter applied before access assembly.",
    )
    run_parser.add_argument(
        "--object-type",
        action="append",
        default=[],
        help="Optional retrieval object type filter. May be passed multiple times.",
    )
    run_parser.add_argument(
        "--status",
        action="append",
        default=[],
        help="Optional retrieval status filter. May be passed multiple times.",
    )
    run_parser.add_argument(
        "--seed-bench-fixtures",
        action="store_true",
        help="Seed the canonical Phase D/Phase I fixture objects when the store is empty.",
    )
    run_parser.set_defaults(_mind_handler=_run_access)

    benchmark_parser = access_subparsers.add_parser(
        "benchmark",
        help="Run AccessDepthBench v1 in an isolated backend.",
        description="Run AccessDepthBench v1 in an isolated backend.",
    )
    _add_common_resolution_args(benchmark_parser)
    benchmark_parser.set_defaults(_mind_handler=_run_access_benchmark)


def _build_governance_selector(args: argparse.Namespace) -> dict[str, Any]:
    selector: dict[str, Any] = {}
    if args.object_id:
        selector["object_ids"] = list(args.object_id)
    if args.provenance_id:
        selector["provenance_ids"] = list(args.provenance_id)
    if args.producer_kind is not None:
        selector["producer_kind"] = args.producer_kind
    if args.producer_id is not None:
        selector["producer_id"] = args.producer_id
    if args.user_id is not None:
        selector["user_id"] = args.user_id
    if args.model_id is not None:
        selector["model_id"] = args.model_id
    if args.episode_id is not None:
        selector["episode_id"] = args.episode_id
    if args.captured_after is not None:
        selector["captured_after"] = args.captured_after
    if args.captured_before is not None:
        selector["captured_before"] = args.captured_before
    return selector


def _run_governance_plan_conceal(args: argparse.Namespace) -> int:
    config = _resolve_cli_config_from_args(args)
    context = _build_primitive_context(args, required_capabilities=(Capability.GOVERNANCE_PLAN,))
    try:
        with _open_cli_store(config) as store:
            result = GovernanceService(store).plan_conceal(
                {
                    "selector": _build_governance_selector(args),
                    "reason": args.reason,
                },
                context,
            )
    except GovernanceServiceError as exc:
        raise SystemExit(str(exc)) from exc

    print("Governance plan conceal")
    print(f"backend={config.backend.value}")
    print(f"operation_id={result.operation_id}")
    print(f"candidate_count={len(result.candidate_object_ids)}")
    print(f"already_concealed_count={len(result.already_concealed_object_ids)}")
    print(
        "selection_json="
        + json.dumps(result.selection, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    )
    for index, object_id in enumerate(result.candidate_object_ids, start=1):
        print(f"candidate_{index}={object_id}")
    return 0


def _run_governance_preview(args: argparse.Namespace) -> int:
    config = _resolve_cli_config_from_args(args)
    context = _build_primitive_context(args, required_capabilities=(Capability.GOVERNANCE_PLAN,))
    try:
        with _open_cli_store(config) as store:
            result = GovernanceService(store).preview_conceal(
                {"operation_id": args.operation_id},
                context,
            )
    except GovernanceServiceError as exc:
        raise SystemExit(str(exc)) from exc

    print("Governance preview conceal")
    print(f"backend={config.backend.value}")
    print(f"operation_id={result.operation_id}")
    print(f"candidate_count={len(result.candidate_object_ids)}")
    print(f"already_concealed_count={len(result.already_concealed_object_ids)}")
    print(f"provenance_summary_count={len(result.provenance_summaries)}")
    for index, object_id in enumerate(result.candidate_object_ids, start=1):
        print(f"candidate_{index}={object_id}")
    summary_items = sorted(result.provenance_summaries.items())
    for index, (object_id, summary) in enumerate(summary_items, start=1):
        print(
            f"summary_{index}="
            f"{object_id}:{summary.producer_kind.value}:{summary.producer_id}:"
            f"{summary.source_channel.value}:{summary.retention_class.value}"
        )
    print(
        "provenance_summaries_json="
        + json.dumps(
            {
                object_id: summary.model_dump(mode="json")
                for object_id, summary in result.provenance_summaries.items()
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


def _run_governance_execute_conceal(args: argparse.Namespace) -> int:
    config = _resolve_cli_config_from_args(args)
    context = _build_primitive_context(args, required_capabilities=(Capability.GOVERNANCE_EXECUTE,))
    try:
        with _open_cli_store(config) as store:
            result = GovernanceService(store).execute_conceal(
                {"operation_id": args.operation_id},
                context,
            )
    except GovernanceServiceError as exc:
        raise SystemExit(str(exc)) from exc

    print("Governance execute conceal")
    print(f"backend={config.backend.value}")
    print(f"operation_id={result.operation_id}")
    print(f"concealed_count={len(result.concealed_object_ids)}")
    print(f"already_concealed_count={len(result.already_concealed_object_ids)}")
    for index, object_id in enumerate(result.concealed_object_ids, start=1):
        print(f"concealed_{index}={object_id}")
    for index, object_id in enumerate(result.already_concealed_object_ids, start=1):
        print(f"already_concealed_{index}={object_id}")
    return 0


def _configure_governance_commands(command_parser: argparse.ArgumentParser) -> None:
    governance_subparsers = command_parser.add_subparsers(
        dest="governance_command",
        metavar="governance-command",
    )

    def add_selector_args(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--object-id",
            action="append",
            default=[],
            help="Optional explicit object id selector. May be passed multiple times.",
        )
        parser.add_argument(
            "--provenance-id",
            action="append",
            default=[],
            help="Optional explicit provenance id selector. May be passed multiple times.",
        )
        parser.add_argument(
            "--producer-kind",
            choices=[kind.value for kind in ProducerKind],
            help="Optional producer kind selector.",
        )
        parser.add_argument("--producer-id", help="Optional producer id selector.")
        parser.add_argument("--user-id", help="Optional user id selector.")
        parser.add_argument("--model-id", help="Optional model id selector.")
        parser.add_argument("--episode-id", help="Optional episode id selector.")
        parser.add_argument(
            "--captured-after",
            help="Optional RFC3339/ISO8601 lower bound on captured_at.",
        )
        parser.add_argument(
            "--captured-before",
            help="Optional RFC3339/ISO8601 upper bound on captured_at.",
        )

    plan_parser = governance_subparsers.add_parser(
        "plan-conceal",
        help="Plan one provenance-aware conceal operation.",
        description="Plan one provenance-aware conceal operation.",
    )
    _add_common_resolution_args(plan_parser)
    _add_common_primitive_context_args(plan_parser)
    add_selector_args(plan_parser)
    plan_parser.add_argument("--reason", required=True, help="Human-readable conceal reason.")
    plan_parser.set_defaults(_mind_handler=_run_governance_plan_conceal)

    preview_parser = governance_subparsers.add_parser(
        "preview",
        help="Preview a planned conceal operation.",
        description="Preview a planned conceal operation.",
    )
    _add_common_resolution_args(preview_parser)
    _add_common_primitive_context_args(preview_parser)
    preview_parser.add_argument(
        "--operation-id",
        required=True,
        help="Existing governance operation id returned by plan-conceal.",
    )
    preview_parser.set_defaults(_mind_handler=_run_governance_preview)

    execute_parser = governance_subparsers.add_parser(
        "execute-conceal",
        help="Execute a planned conceal operation.",
        description="Execute a planned conceal operation.",
    )
    _add_common_resolution_args(execute_parser)
    _add_common_primitive_context_args(execute_parser)
    execute_parser.add_argument(
        "--operation-id",
        required=True,
        help="Existing governance operation id returned by plan-conceal.",
    )
    execute_parser.set_defaults(_mind_handler=_run_governance_execute_conceal)


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
        case
        for case in cases
        if case.task_family is AccessTaskFamily.HIGH_CORRECTNESS
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
            f"job_{index}="
            f"{queued_job.job_id}:{queued_job.job_kind.value}:{queued_job.status.value}"
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


def _require_postgres_dsn(dsn: str | None) -> str:
    if dsn:
        return dsn
    env_dsn = os.environ.get("MIND_POSTGRES_DSN")
    if env_dsn:
        return env_dsn
    raise SystemExit("Provide --dsn or set MIND_POSTGRES_DSN.")


def _run_list_offline_jobs(args: argparse.Namespace) -> int:
    dsn = _require_postgres_dsn(args.dsn)
    statuses = [OfflineJobStatus(status) for status in args.status]
    with PostgresMemoryStore(dsn) as store:
        jobs = store.iter_offline_jobs(statuses=statuses)

    print("Offline jobs")
    print(f"job_count={len(jobs)}")
    for index, job in enumerate(jobs, start=1):
        print(
            f"job_{index}="
            f"{job.job_id}:{job.job_kind.value}:{job.status.value}:{job.priority:.2f}"
        )
    return 0


def _run_offline_worker_command(args: argparse.Namespace) -> int:
    forwarded = [
        "--dsn",
        _require_postgres_dsn(args.dsn),
        "--max-jobs",
        str(args.max_jobs),
        "--worker-id",
        str(args.worker_id),
    ]
    for job_kind in args.job_kind:
        forwarded.extend(("--job-kind", str(job_kind)))
    return offline_worker_main(forwarded)


def _run_enqueue_reflect_episode(args: argparse.Namespace) -> int:
    dsn = _require_postgres_dsn(args.dsn)
    payload = ReflectEpisodeJobPayload(
        episode_id=args.episode_id,
        focus=args.focus,
    )
    job = new_offline_job(
        job_kind=OfflineJobKind.REFLECT_EPISODE,
        payload=payload,
        priority=args.priority,
        max_attempts=args.max_attempts,
    )
    with PostgresMemoryStore(dsn) as store:
        store.enqueue_offline_job(job)

    print("Offline reflect_episode job enqueued")
    print(f"job_id={job.job_id}")
    print(f"episode_id={payload.episode_id}")
    print(f"priority={job.priority:.2f}")
    print(f"max_attempts={job.max_attempts}")
    return 0


def _run_enqueue_promote_schema(args: argparse.Namespace) -> int:
    dsn = _require_postgres_dsn(args.dsn)
    payload = PromoteSchemaJobPayload(
        target_refs=list(args.target_ref),
        reason=args.reason,
    )
    job = new_offline_job(
        job_kind=OfflineJobKind.PROMOTE_SCHEMA,
        payload=payload,
        priority=args.priority,
        max_attempts=args.max_attempts,
    )
    with PostgresMemoryStore(dsn) as store:
        store.enqueue_offline_job(job)

    print("Offline promote_schema job enqueued")
    print(f"job_id={job.job_id}")
    print(f"target_count={len(payload.target_refs)}")
    print(f"priority={job.priority:.2f}")
    print(f"max_attempts={job.max_attempts}")
    return 0


def _run_offline_replay(args: argparse.Namespace) -> int:
    dsn = _require_postgres_dsn(args.dsn)
    if args.top_k < 1:
        raise SystemExit("--top-k must be >= 1.")

    with PostgresMemoryStore(dsn) as store:
        candidate_ids = tuple(args.candidate_id)
        candidate_source = "explicit"
        if args.episode_id:
            candidate_ids = tuple(
                record["id"] for record in store.raw_records_for_episode(args.episode_id)
            )
            candidate_source = f"episode:{args.episode_id}"
        if not candidate_ids:
            raise SystemExit("Provide --candidate-id or --episode-id.")
        ranking = select_replay_targets(
            store,
            candidate_ids,
            top_k=min(args.top_k, len(candidate_ids)),
        )

    print("Offline replay ranking")
    print(f"candidate_source={candidate_source}")
    print(f"candidate_count={len(candidate_ids)}")
    print(f"selected_count={len(ranking)}")
    for index, target in enumerate(ranking, start=1):
        print(f"target_{index}={target.object_id}:{target.score:.4f}")
    return 0


def _configure_offline_commands(command_parser: argparse.ArgumentParser) -> None:
    offline_subparsers = command_parser.add_subparsers(
        dest="offline_command",
        metavar="offline-command",
    )

    worker_parser = offline_subparsers.add_parser(
        "worker",
        help="Run one offline maintenance worker batch.",
        description="Run one offline maintenance worker batch against PostgreSQL.",
    )
    worker_parser.add_argument(
        "--dsn",
        default=os.environ.get("MIND_POSTGRES_DSN"),
        help="PostgreSQL DSN. Falls back to MIND_POSTGRES_DSN.",
    )
    worker_parser.add_argument(
        "--max-jobs",
        type=int,
        default=1,
        help="Maximum number of jobs to claim in this batch.",
    )
    worker_parser.add_argument(
        "--worker-id",
        default="mind-offline-worker",
        help="Worker identifier to stamp on claimed jobs.",
    )
    worker_parser.add_argument(
        "--job-kind",
        action="append",
        choices=[job_kind.value for job_kind in OfflineJobKind],
        default=[],
        help="Optional job kind filter. May be passed multiple times.",
    )
    worker_parser.set_defaults(_mind_handler=_run_offline_worker_command)

    list_jobs_parser = offline_subparsers.add_parser(
        "list-jobs",
        help="Inspect offline jobs currently persisted in PostgreSQL.",
        description="Inspect offline jobs currently persisted in PostgreSQL.",
    )
    list_jobs_parser.add_argument(
        "--dsn",
        default=os.environ.get("MIND_POSTGRES_DSN"),
        help="PostgreSQL DSN. Falls back to MIND_POSTGRES_DSN.",
    )
    list_jobs_parser.add_argument(
        "--status",
        action="append",
        choices=[status.value for status in OfflineJobStatus],
        default=[],
        help="Optional job status filter. May be passed multiple times.",
    )
    list_jobs_parser.set_defaults(_mind_handler=_run_list_offline_jobs)

    reflect_episode_parser = offline_subparsers.add_parser(
        "reflect-episode",
        help="Enqueue one reflect_episode offline job.",
        description="Enqueue one reflect_episode offline job into PostgreSQL.",
    )
    reflect_episode_parser.add_argument(
        "--dsn",
        default=os.environ.get("MIND_POSTGRES_DSN"),
        help="PostgreSQL DSN. Falls back to MIND_POSTGRES_DSN.",
    )
    reflect_episode_parser.add_argument("--episode-id", required=True, help="Target episode id.")
    reflect_episode_parser.add_argument(
        "--focus",
        default="offline replay reflection",
        help="Reflection focus stored in the queued payload.",
    )
    reflect_episode_parser.add_argument(
        "--priority",
        type=float,
        default=0.5,
        help="Job priority in the [0, 1] range.",
    )
    reflect_episode_parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Maximum offline worker attempts for the queued job.",
    )
    reflect_episode_parser.set_defaults(_mind_handler=_run_enqueue_reflect_episode)

    promote_schema_parser = offline_subparsers.add_parser(
        "promote-schema",
        help="Enqueue one promote_schema offline job.",
        description="Enqueue one promote_schema offline job into PostgreSQL.",
    )
    promote_schema_parser.add_argument(
        "--dsn",
        default=os.environ.get("MIND_POSTGRES_DSN"),
        help="PostgreSQL DSN. Falls back to MIND_POSTGRES_DSN.",
    )
    promote_schema_parser.add_argument(
        "--target-ref",
        action="append",
        required=True,
        default=[],
        help="Target object id to include in the promotion job. May be passed multiple times.",
    )
    promote_schema_parser.add_argument(
        "--reason",
        required=True,
        help="Human-readable reason stored in the queued payload.",
    )
    promote_schema_parser.add_argument(
        "--priority",
        type=float,
        default=0.5,
        help="Job priority in the [0, 1] range.",
    )
    promote_schema_parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Maximum offline worker attempts for the queued job.",
    )
    promote_schema_parser.set_defaults(_mind_handler=_run_enqueue_promote_schema)

    replay_parser = offline_subparsers.add_parser(
        "replay",
        help="Inspect replay target ranking for a candidate pool.",
        description="Inspect replay target ranking for a candidate pool in PostgreSQL.",
    )
    replay_parser.add_argument(
        "--dsn",
        default=os.environ.get("MIND_POSTGRES_DSN"),
        help="PostgreSQL DSN. Falls back to MIND_POSTGRES_DSN.",
    )
    replay_parser.add_argument(
        "--candidate-id",
        action="append",
        default=[],
        help="Candidate object id to rank. May be passed multiple times.",
    )
    replay_parser.add_argument(
        "--episode-id",
        help="Optional episode id used to derive candidate raw records.",
    )
    replay_parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Maximum number of ranked replay targets to print.",
    )
    replay_parser.set_defaults(_mind_handler=_run_offline_replay)


def _resolve_cli_config_from_args(args: argparse.Namespace) -> ResolvedCliConfig:
    return resolve_cli_config(
        profile=getattr(args, "profile", None),
        backend=getattr(args, "backend", None),
        sqlite_path=getattr(args, "sqlite_path", None),
        postgres_dsn=getattr(args, "dsn", None),
    )


def _run_config_show(args: argparse.Namespace) -> int:
    config = _resolve_cli_config_from_args(args)
    print("CLI config")
    print(f"requested_profile={config.requested_profile.value}")
    print(f"requested_profile_source={config.requested_profile_source}")
    print(f"resolved_profile={config.resolved_profile.value}")
    print(f"backend={config.backend.value}")
    print(f"backend_source={config.backend_source}")
    if config.sqlite_path is not None and config.sqlite_path_source is not None:
        print(f"sqlite_path={config.sqlite_path.as_posix()}")
        print(f"sqlite_path_source={config.sqlite_path_source}")
    if config.postgres_dsn is not None and config.postgres_dsn_source is not None:
        print(f"postgres_dsn={redact_dsn(config.postgres_dsn)}")
        print(f"postgres_dsn_source={config.postgres_dsn_source}")
    elif config.postgres_dsn_source is not None:
        print("postgres_dsn=unset")
        print(f"postgres_dsn_source={config.postgres_dsn_source}")
    return 0


def _run_config_profile(args: argparse.Namespace) -> int:
    profiles = list_cli_profiles()
    selected_name = getattr(args, "name", None)
    if selected_name is not None:
        selected_profile = CliProfile(selected_name)
        profiles = tuple(
            profile for profile in profiles if profile.profile is selected_profile
        )

    print("CLI profiles")
    print(f"profile_count={len(profiles)}")
    for index, profile in enumerate(profiles, start=1):
        env_hint = profile.env_hint or "none"
        print(
            f"profile_{index}="
            f"{profile.profile.value}:{profile.default_backend.value}:{env_hint}:{profile.description}"
        )
    return 0


def _run_config_doctor(args: argparse.Namespace) -> int:
    config = _resolve_cli_config_from_args(args)
    checks = build_config_doctor_checks(config)
    overall_status = "ok" if all(check.status == "ok" for check in checks) else "warn"
    print("CLI config doctor")
    print(f"overall_status={overall_status}")
    for index, check in enumerate(checks, start=1):
        print(f"check_{index}={check.name}:{check.status}:{check.detail}")
    return 0


def _configure_config_commands(command_parser: argparse.ArgumentParser) -> None:
    config_subparsers = command_parser.add_subparsers(
        dest="config_command",
        metavar="config-command",
    )

    show_parser = config_subparsers.add_parser(
        "show",
        help="Resolve and print the active CLI config.",
        description="Resolve and print the active CLI profile/backend configuration.",
    )
    _add_common_resolution_args(show_parser)
    show_parser.set_defaults(_mind_handler=_run_config_show)

    profile_parser = config_subparsers.add_parser(
        "profile",
        help="Inspect the frozen CLI profile catalog.",
        description="Inspect the frozen CLI profile catalog.",
    )
    profile_parser.add_argument(
        "--name",
        choices=[profile.value for profile in CliProfile],
        help="Optional single profile to inspect.",
    )
    profile_parser.set_defaults(_mind_handler=_run_config_profile)

    doctor_parser = config_subparsers.add_parser(
        "doctor",
        help="Run a lightweight CLI config diagnostic.",
        description="Run a lightweight CLI config diagnostic.",
    )
    _add_common_resolution_args(doctor_parser)
    doctor_parser.set_defaults(_mind_handler=_run_config_doctor)


def _run_acceptance_report(args: argparse.Namespace) -> int:
    phase = args.phase
    report_path = _ACCEPTANCE_REPORTS[phase]
    relative_path = report_path.relative_to(_REPO_ROOT)
    print("Acceptance report")
    print(f"phase={phase}")
    print(f"report_path={relative_path}")
    print(f"exists={'true' if report_path.exists() else 'false'}")
    return 0


def _configure_report_commands(command_parser: argparse.ArgumentParser) -> None:
    report_subparsers = command_parser.add_subparsers(
        dest="report_command",
        metavar="report-command",
    )

    phase_f_manifest_parser = report_subparsers.add_parser(
        "phase-f-manifest",
        help="Print the frozen LongHorizonEval v1 manifest.",
        description="Print the frozen LongHorizonEval v1 manifest.",
    )
    phase_f_manifest_parser.set_defaults(
        _mind_handler=_run_no_argv_command(benchmark_manifest_main)
    )

    phase_f_baselines_parser = report_subparsers.add_parser(
        "phase-f-baselines",
        help="Run the three frozen Phase F baselines once.",
        description="Run the three frozen Phase F baselines once on LongHorizonEval v1.",
    )
    phase_f_baselines_parser.set_defaults(
        _mind_handler=_run_no_argv_command(benchmark_baselines_main)
    )

    phase_f_ci_parser = report_subparsers.add_parser(
        "phase-f-ci",
        help="Run repeated Phase F baselines and persist the CI report.",
        description="Run repeated Phase F baselines and persist the CI report.",
    )
    phase_f_ci_parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="Independent run count for each system. Must be >= 3 for F-3.",
    )
    phase_f_ci_parser.add_argument(
        "--output",
        default="artifacts/phase_f/baseline_report.json",
        help="Output path for the persisted JSON report.",
    )
    phase_f_ci_parser.set_defaults(
        _mind_handler=_run_forwarded_command(
            benchmark_report_main,
            (("repeat_count", "--repeat-count"), ("output", "--output")),
        )
    )

    phase_f_comparison_parser = report_subparsers.add_parser(
        "phase-f-comparison",
        help="Run the Phase F comparison report.",
        description="Run the current MIND system against the Phase F baselines.",
    )
    phase_f_comparison_parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="Independent run count for each system. Must be >= 3.",
    )
    phase_f_comparison_parser.add_argument(
        "--output",
        default="artifacts/phase_f/comparison_report.json",
        help="Output path for the persisted comparison JSON report.",
    )
    phase_f_comparison_parser.set_defaults(
        _mind_handler=_run_forwarded_command(
            benchmark_comparison_main,
            (("repeat_count", "--repeat-count"), ("output", "--output")),
        )
    )

    phase_g_cost_parser = report_subparsers.add_parser(
        "phase-g-cost",
        help="Run the Phase G cost report.",
        description="Run the Phase G fixed-rule strategy cost report skeleton.",
    )
    phase_g_cost_parser.add_argument(
        "--repeat-count",
        type=int,
        default=3,
        help="Independent run count for cost accounting. Must be >= 1.",
    )
    phase_g_cost_parser.add_argument(
        "--output",
        default="artifacts/phase_g/cost_report.json",
        help="Output path for the persisted Phase G cost report JSON.",
    )
    phase_g_cost_parser.set_defaults(
        _mind_handler=_run_forwarded_command(
            strategy_cost_report_main,
            (("repeat_count", "--repeat-count"), ("output", "--output")),
        )
    )

    acceptance_parser = report_subparsers.add_parser(
        "acceptance",
        help="Inspect the frozen acceptance-report path for a phase.",
        description="Inspect the frozen acceptance-report path for a phase.",
    )
    acceptance_parser.add_argument(
        "--phase",
        choices=sorted(_ACCEPTANCE_REPORTS),
        required=True,
        help="Phase identifier with a frozen acceptance report.",
    )
    acceptance_parser.set_defaults(_mind_handler=_run_acceptance_report)


def build_mind_parser() -> argparse.ArgumentParser:
    """Build the unified top-level `mind` parser."""

    parser = argparse.ArgumentParser(
        prog="mindtest",
        description=(
            "Unified CLI for exploring MIND primitives, runtime access, offline "
            "maintenance, governance, gates, reports, demos, and configuration."
        ),
        epilog=_format_examples(
            (
                "mindtest primitive -h",
                "mindtest access -h",
                "mindtest gate -h",
                "mindtest demo -h",
            )
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"mindtest {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    for group in _MIND_COMMAND_GROUPS:
        command_parser = subparsers.add_parser(
            group.name,
            help=group.help,
            description=group.description,
            epilog=_format_examples(group.examples),
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        command_parser.set_defaults(_mind_parser=command_parser, _mind_handler=_print_bound_help)
        if group.name == "primitive":
            _configure_primitive_commands(command_parser)
        if group.name == "access":
            _configure_access_commands(command_parser)
        if group.name == "governance":
            _configure_governance_commands(command_parser)
        if group.name == "offline":
            _configure_offline_commands(command_parser)
        if group.name == "demo":
            _configure_demo_commands(command_parser)
        if group.name == "gate":
            _configure_gate_commands(command_parser)
        if group.name == "report":
            _configure_report_commands(command_parser)
        if group.name == "config":
            _configure_config_commands(command_parser)

    return parser


def mind_main(argv: Sequence[str] | None = None) -> int:
    """Run the unified Phase J top-level CLI help skeleton."""

    parser = build_mind_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    handler = getattr(args, "_mind_handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return handler(args)


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
    print(
        "phase_c_schema="
        f"{primitive_result.schema_valid_calls}/{primitive_result.total_calls}"
    )
    print(
        "phase_c_budget_rejections="
        f"{primitive_result.budget_rejection_match_count}/{primitive_result.budget_total}"
    )
    print(
        "phase_c_rollback_atomic="
        f"{primitive_result.rollback_atomic_count}/{primitive_result.rollback_total}"
    )
    print(
        "phase_d_recall_at_20="
        f"{workspace_result.candidate_recall_at_20:.2f}"
    )
    print(
        "phase_d_workspace_coverage="
        f"{workspace_result.workspace_gold_fact_coverage:.2f}"
    )
    print(
        "phase_d_workspace_discipline="
        f"{workspace_result.workspace_slot_discipline_rate:.2f}"
    )
    print(
        "phase_d_token_cost_ratio="
        f"{workspace_result.median_token_cost_ratio:.2f}"
    )
    print(
        "phase_d_task_success_drop_pp="
        f"{workspace_result.task_success_drop_pp:.2f}"
    )
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
    print(
        "phase_e_pollution_rate_delta="
        f"{offline_result.dev_eval.pollution_rate_delta:.2f}"
    )
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
    print(
        "fixed_lock_overrides="
        f"{result.fixed_lock_override_count}/{result.fixed_lock_run_count}"
    )
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
    print(
        "family_reachability="
        f"{result.family_reachability_count}/{result.family_total}"
    )
    print(
        "representative_flows="
        f"{result.representative_flow_pass_count}/{result.representative_flow_total}"
    )
    print(f"postgres_demo_configured={str(result.postgres_demo_configured).lower()}")
    print(
        "config_audit="
        f"{result.config_audit_pass_count}/{result.config_audit_total}"
    )
    print(
        "output_contracts="
        f"{result.output_contract_pass_count}/{result.output_contract_total}"
    )
    print(
        "invalid_exit_contracts="
        f"{result.invalid_exit_coverage_count}/{result.invalid_exit_total}"
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


def benchmark_manifest_main() -> int:
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


def benchmark_baselines_main() -> int:
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


def benchmark_report_main(argv: Sequence[str] | None = None) -> int:
    """Run repeated Phase F baselines and persist the CI report."""

    parser = argparse.ArgumentParser(
        prog="mindtest-phase-f-report",
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


def benchmark_comparison_main(argv: Sequence[str] | None = None) -> int:
    """Run the current MIND system against the Phase F baselines."""

    parser = argparse.ArgumentParser(
        prog="mindtest-phase-f-comparison",
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

    result = evaluate_benchmark_comparison(repeat_count=args.repeat_count)
    try:
        assert_benchmark_comparison(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    output_path = write_benchmark_comparison_report_json(args.output, result)
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
    print(f"phase_f_comparison={'PASS' if result.benchmark_comparison_pass else 'FAIL'}")
    return 0


def benchmark_gate_main(argv: Sequence[str] | None = None) -> int:
    """Run the full local Phase F gate, including F-7 ablations."""

    parser = argparse.ArgumentParser(
        prog="mindtest-phase-f-gate",
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

    result = evaluate_benchmark_gate(repeat_count=args.repeat_count)
    try:
        assert_benchmark_gate(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    output_path = write_benchmark_gate_report_json(args.output, result)
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
    print(f"phase_f_gate={'PASS' if result.benchmark_gate_pass else 'FAIL'}")
    return 0


def strategy_cost_report_main(argv: Sequence[str] | None = None) -> int:
    """Run the Phase G fixed-rule strategy cost report skeleton."""

    parser = argparse.ArgumentParser(
        prog="mindtest-phase-g-cost-report",
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
    output_path = write_strategy_cost_report_json(args.output, result)
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


def strategy_dev_main(argv: Sequence[str] | None = None) -> int:
    """Run a local fixed-rule vs optimized-v1 dev comparison."""

    parser = argparse.ArgumentParser(
        prog="mindtest-phase-g-strategy-dev",
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


def strategy_gate_main(argv: Sequence[str] | None = None) -> int:
    """Run the formal Phase G local gate."""

    parser = argparse.ArgumentParser(
        prog="mindtest-phase-g-gate",
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

    result = evaluate_strategy_gate(repeat_count=args.repeat_count)
    try:
        assert_strategy_gate(result)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    output_path = write_strategy_gate_report_json(args.output, result)
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
    print(f"phase_g_gate={'PASS' if result.strategy_gate_pass else 'FAIL'}")
    return 0
