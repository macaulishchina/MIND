"""CLI subcommands for primitive, access, and governance operations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .access import (
    AccessMode,
    AccessService,
    AccessTaskFamily,
    evaluate_access_benchmark,
)
from .cli import (
    _ACCESS_QUERY_MODES,
    _SUMMARY_SCOPES,
    _add_common_primitive_context_args,
    _add_common_resolution_args,
    _build_primitive_context,
    _execute_primitive,
    _open_cli_store,
    _parse_json_argument,
    _parse_text_or_json_value,
    _resolve_cli_config_from_args,
)
from .cli_config import CliBackend, ResolvedCliConfig, redact_dsn
from .fixtures.retrieval_benchmark import build_canonical_seed_objects
from .governance import GovernanceService, GovernanceServiceError
from .kernel.postgres_store import (
    PostgresMemoryStore,
    build_postgres_store_factory,
    run_postgres_migrations,
    temporary_postgres_database,
)
from .kernel.provenance import ProducerKind
from .kernel.schema import VALID_RECORD_KIND
from .kernel.store import SQLiteMemoryStore
from .primitives import Capability


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


