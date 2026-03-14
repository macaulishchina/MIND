"""Project CLI entry points."""

from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .capabilities.port_adapter import CapabilityPortAdapter
from .cli_config import (
    CliBackend,
    CliProfile,
    ResolvedCliConfig,
    redact_dsn,
    resolve_cli_config,
)
from .kernel.postgres_store import (
    PostgresMemoryStore,
    run_postgres_migrations,
    temporary_postgres_database,
)
from .kernel.store import SQLiteMemoryStore
from .primitives import Capability, PrimitiveExecutionContext, PrimitiveName, PrimitiveOutcome
from .primitives.service import PrimitiveService


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
_LIVE_CAPABILITY_PROVIDER_CHOICES: tuple[str, ...] = ("openai", "claude", "gemini")
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
            "mindtest gate phase-k --help",
            "mindtest gate phase-m --help",
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
            "mindtest report phase-k-compatibility --help",
            "mindtest report product-readiness --help",
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
        if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
            for item in value:
                forwarded.extend((flag, str(item)))
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
        service = PrimitiveService(
            store,
            capability_service=CapabilityPortAdapter(),
        )
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


def _resolve_cli_config_from_args(args: argparse.Namespace) -> ResolvedCliConfig:
    return resolve_cli_config(
        profile=getattr(args, "profile", None),
        backend=getattr(args, "backend", None),
        sqlite_path=getattr(args, "sqlite_path", None),
        postgres_dsn=getattr(args, "dsn", None),
        allow_sqlite=True,
    )


# ── imports from extracted CLI modules (placed after shared helpers) ──
from .cli_demo_cmds import _configure_demo_commands, _configure_gate_commands  # noqa: E402

# Re-export gate entry points so pyproject.toml console_scripts and test
# monkeypatches continue to resolve via ``mind.cli:<name>``.
from .cli_gates import (  # noqa: E402, F401
    access_gate_main,
    capability_compatibility_report_main,
    capability_gate_main,
    cli_gate_main,
    governance_gate_main,
    kernel_gate_main,
    offline_gate_main,
    offline_startup_main,
    offline_worker_main,
    postgres_regression_main,
    primitive_gate_main,
    product_transport_report_main,
    workspace_smoke_main,
)
from .cli_ops_cmds import (  # noqa: E402
    _configure_config_commands,
    _configure_offline_commands,
    _configure_report_commands,
)
from .cli_phase_gates import (  # noqa: E402, F401
    benchmark_baselines_main,
    benchmark_comparison_main,
    benchmark_gate_main,
    benchmark_manifest_main,
    benchmark_report_main,
    deployment_smoke_report_main,
    frontend_gate_main,
    product_readiness_gate_main,
    product_readiness_report_main,
    strategy_cost_report_main,
    strategy_dev_main,
    strategy_gate_main,
)
from .cli_primitive_cmds import (  # noqa: E402
    _configure_access_commands,
    _configure_governance_commands,
    _configure_primitive_commands,
)


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


