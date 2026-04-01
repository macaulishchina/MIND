from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mind.config import ConfigManager
from mind.config.manager import _DEFAULT_TEST_TOML
from mind.config.models import MemoryItem, OwnerContext
from mind.llms.factory import LlmFactory
from mind.memory import Memory
from mind.runtime_logging import configure_runtime_logging
from mind.stl.parser import parse_program
from mind.stl.prompt import (
    STL_EXTRACTION_SYSTEM_PROMPT,
    STL_EXTRACTION_USER_TEMPLATE,
    format_focus_stack,
)
from mind.stl.models import ParseLevel
from mind.utils import parse_messages


# ── helpers ──────────────────────────────────────────────────────────


def _count_strict_lines(program) -> tuple[int, int]:
    """Return (strict_count, total_count) for parsed elements in a program."""
    all_items = list(program.refs) + list(program.statements) + list(program.notes)
    total = len(all_items) + len(program.failed_lines)
    strict = sum(1 for item in all_items if getattr(item, "parse_level", None) == ParseLevel.STRICT)
    return strict, total

DEFAULT_CASES_DIR = PROJECT_ROOT / "tests" / "eval" / "cases"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "tests" / "eval" / "reports"
OWNER_ADD_TARGETS = {
    "canonical_text_accuracy": 0.95,
    "subject_ref_accuracy": 0.95,
    "count_accuracy": 0.95,
    "owner_accuracy": 1.00,
    "case_pass_rate": 0.95,
}
STL_EXTRACT_TARGETS = {
    "ref_accuracy": 0.90,
    "statement_accuracy": 0.90,
    "stl_syntax_rate": 0.90,
    "case_pass_rate": 0.90,
}
SUPPORTED_STAGES = ("owner_add", "stl_extract")


@dataclass
class DatasetSpec:
    path: Path
    name: str
    cases: list[dict[str, Any]]


@dataclass
class OwnerAddCaseResult:
    case_id: str
    description: str
    owner_pass: bool
    count_pass: bool
    active_count: int
    expected_active_count: int | None
    canonical_hits: int
    canonical_total: int
    subject_hits: int
    subject_total: int
    case_pass: bool
    failures: list[str]
    active_memories: list[dict[str, Any]]


@dataclass
class StlExtractCaseResult:
    case_id: str
    description: str
    ref_hits: int
    ref_total: int
    statement_hits: int
    statement_total: int
    strict_lines: int
    total_lines: int
    case_pass: bool
    failures: list[str]
    refs: list[dict[str, Any]]
    statements: list[dict[str, Any]]
    stl_text: str
    expected_stl: str


def _configure_runner_logging(cfg) -> None:
    configure_runtime_logging(cfg.logging)


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


def _safe_ratio(numerator: int, denominator: int, empty_value: float = 1.0) -> float:
    if denominator == 0:
        return empty_value
    return numerator / denominator


def _sanitize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", value.casefold()).strip("-") or "case"


def _infer_suite(case_id: str) -> str:
    if case_id.startswith("owner-add-"):
        return "add"
    if case_id.startswith("owner-feature-"):
        return "feature"
    if case_id.startswith("owner-rel-"):
        return "relationship"
    if case_id.startswith("owner-comprehensive-"):
        return "comprehensive"
    return "misc"


def _load_case_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if "stages" not in payload:
        raise ValueError(f"Case {path} is missing required 'stages' block")
    payload.setdefault("suite", _infer_suite(payload.get("id", path.stem)))
    return payload


def _load_dataset(source: Path) -> DatasetSpec:
    resolved = source.resolve()
    if resolved.is_dir():
        case_files = sorted(resolved.glob("*.json"))
        cases = [_load_case_file(p) for p in case_files]
        return DatasetSpec(path=resolved, name=resolved.name, cases=cases)
    if not resolved.exists():
        sys.exit(f"Error: case file not found: {resolved}")
    return DatasetSpec(path=resolved, name=resolved.stem, cases=[_load_case_file(resolved)])


def _resolve_dataset_path(case_arg: Path | None) -> Path:
    return case_arg.resolve() if case_arg is not None else DEFAULT_CASES_DIR


def _case_owner_context(case: dict[str, Any]) -> OwnerContext:
    return OwnerContext(**case.get("owner", {}))


def _case_owner_lookup(case: dict[str, Any]) -> str:
    owner = case.get("owner", {})
    return owner.get("external_user_id") or owner.get("anonymous_session_id") or ""


def _case_messages(case: dict[str, Any]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for turn in case.get("turns", []):
        messages.extend(turn.get("messages", []))
    return messages


def _case_stage(case: dict[str, Any], stage: str) -> dict[str, Any] | None:
    return case.get("stages", {}).get(stage)


def _cases_for_stage(dataset: DatasetSpec, stage: str) -> DatasetSpec:
    selected = [case for case in dataset.cases if _case_stage(case, stage)]
    return DatasetSpec(path=dataset.path, name=dataset.name, cases=selected)


def _eval_config(cfg, case_id: str, temp_dir: str):
    eval_cfg = cfg.model_copy(deep=True)
    eval_cfg.vector_store.provider = "qdrant"
    eval_cfg.vector_store.collection_name = f"eval_{_sanitize_name(case_id)}"
    eval_cfg.vector_store.url = ""
    eval_cfg.vector_store.api_key = ""
    eval_cfg.vector_store.dsn = ""
    eval_cfg.vector_store.on_disk = False
    eval_cfg.history_store.provider = "sqlite"
    eval_cfg.history_store.db_path = str(Path(temp_dir) / "history.db")
    eval_cfg.stl_store.provider = "sqlite"
    eval_cfg.stl_store.db_path = str(Path(temp_dir) / "stl.db")
    return eval_cfg


def _serialize_item(item: MemoryItem) -> dict[str, Any]:
    payload = item.model_dump()
    family = payload.get("fact_family")
    if hasattr(family, "value"):
        payload["fact_family"] = family.value
    status = payload.get("status")
    if hasattr(status, "value"):
        payload["status"] = status.value
    return payload


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if hasattr(value, "value") and not isinstance(value, (str, bytes)):
        try:
            return value.value
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return value


def _memory_matches(item: MemoryItem, expectation: dict[str, Any]) -> bool:
    if expectation.get("canonical_text") and item.canonical_text != expectation["canonical_text"]:
        return False
    if expectation.get("canonical_text_contains") and expectation["canonical_text_contains"] not in (item.canonical_text or ""):
        return False
    if expectation.get("subject_ref") and item.subject_ref != expectation["subject_ref"]:
        return False
    if expectation.get("field_key") and item.field_key != expectation["field_key"]:
        return False
    if expectation.get("relation_type") and item.relation_type != expectation["relation_type"]:
        return False
    if expectation.get("fact_family"):
        actual_family = item.fact_family.value if getattr(item.fact_family, "value", None) else item.fact_family
        if actual_family != expectation["fact_family"]:
            return False
    return True


def _ref_matches(row: dict[str, Any], expectation: dict[str, Any]) -> bool:
    for key in ("scope", "ref_type", "key"):
        if key in expectation and row.get(key) != expectation[key]:
            return False
    return True


def _statement_matches(row: dict[str, Any], expectation: dict[str, Any]) -> bool:
    if expectation.get("predicate") and row.get("predicate") != expectation["predicate"]:
        return False
    if expectation.get("category") and row.get("category") != expectation["category"]:
        return False
    rendered_args = row.get("args", [])
    if "args" in expectation and rendered_args != expectation["args"]:
        return False
    flat_args = json.dumps(rendered_args, ensure_ascii=False)
    args_contains = expectation.get("args_contains", [])
    if args_contains and not all(str(label) in flat_args for label in args_contains):
        return False
    return True


def _stored_ref_rows(memory: Memory, owner_id: str) -> list[dict[str, Any]]:
    conn = memory._stl_store._get_conn()
    rows = conn.execute(
        """SELECT id, scope, ref_type, key, aliases
           FROM refs WHERE owner_id = ?
           ORDER BY id""",
        (owner_id,),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        aliases = item.get("aliases")
        if isinstance(aliases, str):
            item["aliases"] = json.loads(aliases)
        result.append(item)
    return result


def _render_stored_arg(arg: Any, refs_by_id: dict[str, dict[str, Any]]) -> Any:
    if isinstance(arg, list):
        return [_render_stored_arg(item, refs_by_id) for item in arg]
    if not isinstance(arg, str):
        return arg
    if not arg.startswith("@"):
        return arg
    ref_id = arg[1:]
    row = refs_by_id.get(ref_id)
    if row is None:
        return arg
    if row.get("scope") == "self":
        return "@self"
    ref_type = row.get("ref_type")
    key = row.get("key")
    if ref_type and key:
        return f'@{ref_type}("{key}")'
    return arg


def _stored_statement_rows(memory: Memory, owner_id: str, refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs_by_id = {row["id"]: row for row in refs}
    rows = memory._stl_store.query_statements(owner_id=owner_id, is_current=True, limit=500)
    rendered = []
    for row in rows:
        rendered.append(
            {
                **row,
                "args": [_render_stored_arg(arg, refs_by_id) for arg in row.get("args", [])],
            }
        )
    return rendered


def _render_parsed_ref_expr(expr: Any) -> str:
    scope = getattr(getattr(expr, "scope", None), "value", getattr(expr, "scope", None))
    if scope == "self":
        return "@self"
    ref_type = getattr(expr, "ref_type", None)
    key = getattr(expr, "key", None)
    if ref_type and key is not None:
        return f'@{str(ref_type).casefold()}("{key}")'
    if ref_type:
        return f"@{str(ref_type).casefold()}"
    return "@unknown"


def _render_parsed_arg(arg: Any, refs_by_local_id: dict[str, Any]) -> Any:
    kind = getattr(arg, "kind", None)
    if kind == "ref":
        if arg.ref_id in {"s", "self"}:
            return "@self"
        expr = refs_by_local_id.get(arg.ref_id)
        if expr is not None:
            return _render_parsed_ref_expr(expr)
        return f"@{arg.ref_id}"
    if kind == "prop":
        return f"${arg.prop_id}"
    if kind == "number":
        value = arg.value
        return int(value) if isinstance(value, float) and value.is_integer() else value
    if kind == "literal":
        return arg.value
    return str(arg)


def _parsed_ref_rows(program) -> list[dict[str, Any]]:
    rows = []
    for ref in program.refs:
        expr = ref.expr
        rows.append(
            {
                "id": ref.local_id,
                "scope": getattr(expr.scope, "value", expr.scope),
                "ref_type": str(expr.ref_type).casefold() if expr.ref_type else None,
                "key": expr.key,
                "aliases": [],
            }
        )
    return rows


def _parsed_statement_rows(program) -> list[dict[str, Any]]:
    refs_by_local_id = {ref.local_id: ref.expr for ref in program.refs}
    rows = []
    for stmt in program.statements:
        rendered_args = [_render_parsed_arg(arg, refs_by_local_id) for arg in stmt.args]
        inferred_category = stmt.category
        if inferred_category is None and any(
            isinstance(arg, str) and arg.startswith("$") for arg in rendered_args
        ):
            inferred_category = "frame"
        rows.append(
            {
                "id": stmt.local_id,
                "predicate": stmt.predicate,
                "category": inferred_category,
                "args": rendered_args,
            }
        )
    return rows


def _build_stl_messages(case: dict[str, Any]) -> list[dict[str, str]]:
    conversation = parse_messages(_case_messages(case))
    focus_stack_text = format_focus_stack([])
    return [
        {"role": "system", "content": STL_EXTRACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": STL_EXTRACTION_USER_TEMPLATE.format(
                focus_stack=focus_stack_text,
                conversation=conversation,
            ),
        },
    ]


def _evaluate_owner_add_case(cfg, case: dict[str, Any]) -> OwnerAddCaseResult:
    stage = _case_stage(case, "owner_add") or {}
    failures: list[str] = []
    owner_context = _case_owner_context(case)
    owner_lookup = _case_owner_lookup(case)

    with tempfile.TemporaryDirectory(prefix=f"owner_eval_{_sanitize_name(case['id'])}_") as temp_dir:
        eval_cfg = _eval_config(cfg, case["id"], temp_dir)
        memory = Memory(eval_cfg)
        try:
            memory.add(messages=_case_messages(case), owner=owner_context)
            owner_record = memory._history_store.resolve_owner(owner_context)
            active_memories = memory.get_all(owner_lookup, limit=500)
        finally:
            memory.close()

    owner_pass = all(item.owner_id == owner_record.owner_id for item in active_memories)
    if not owner_pass:
        failures.append("owner:mismatch")

    expected_active_count = stage.get("expected_active_count")
    count_pass = True
    if expected_active_count is not None:
        count_pass = len(active_memories) == expected_active_count
        if not count_pass:
            failures.append(f"count:{len(active_memories)} != {expected_active_count}")

    canonical_hits = 0
    canonical_total = 0
    subject_hits = 0
    subject_total = 0
    for expected in stage.get("expected_active_memories", []):
        if "canonical_text" in expected or "canonical_text_contains" in expected:
            canonical_total += 1
        if "subject_ref" in expected:
            subject_total += 1
        matched = next((item for item in active_memories if _memory_matches(item, expected)), None)
        if matched is None:
            failures.append(
                f"missing_active:{expected.get('canonical_text') or expected.get('canonical_text_contains') or expected}"
            )
            continue
        if "canonical_text" in expected or "canonical_text_contains" in expected:
            canonical_hits += 1
        if "subject_ref" in expected:
            subject_hits += 1

    return OwnerAddCaseResult(
        case_id=case["id"],
        description=case.get("description", ""),
        owner_pass=owner_pass,
        count_pass=count_pass,
        active_count=len(active_memories),
        expected_active_count=expected_active_count,
        canonical_hits=canonical_hits,
        canonical_total=canonical_total,
        subject_hits=subject_hits,
        subject_total=subject_total,
        case_pass=not failures,
        failures=failures,
        active_memories=[_serialize_item(item) for item in active_memories],
    )


def _evaluate_stl_extract_case(cfg, case: dict[str, Any]) -> StlExtractCaseResult:
    stage = _case_stage(case, "stl_extract") or {}
    llm_cfg = cfg.llm_stages.get("stl_extraction", cfg.llm)
    llm = LlmFactory.create(llm_cfg)
    messages = _build_stl_messages(case)
    stl_text = llm.generate(messages=messages)
    program = parse_program(stl_text, batch_id=_sanitize_name(case["id"]))

    refs = _parsed_ref_rows(program)
    statements = _parsed_statement_rows(program)
    strict_lines, total_lines = _count_strict_lines(program)
    expected_stl = stage.get("expected_stl", "")
    failures: list[str] = []

    ref_hits = 0
    ref_total = 0
    for expected in stage.get("expected_refs", []):
        ref_total += 1
        if any(_ref_matches(row, expected) for row in refs):
            ref_hits += 1
        else:
            failures.append(f"missing_ref:{expected}")

    statement_hits = 0
    statement_total = 0
    for expected in stage.get("expected_statements", []):
        statement_total += 1
        if any(_statement_matches(row, expected) for row in statements):
            statement_hits += 1
        else:
            failures.append(f"missing_statement:{expected}")

    return StlExtractCaseResult(
        case_id=case["id"],
        description=case.get("description", ""),
        ref_hits=ref_hits,
        ref_total=ref_total,
        statement_hits=statement_hits,
        statement_total=statement_total,
        strict_lines=strict_lines,
        total_lines=total_lines,
        case_pass=not failures,
        failures=failures,
        refs=refs,
        statements=statements,
        stl_text=stl_text,
        expected_stl=expected_stl,
    )


def _evaluate_cases(dataset: DatasetSpec, evaluator, concurrency: int) -> list[Any]:
    if concurrency <= 1 or len(dataset.cases) <= 1:
        return [evaluator(case) for case in dataset.cases]
    ordered_results: list[Any | None] = [None] * len(dataset.cases)
    with ThreadPoolExecutor(max_workers=min(concurrency, len(dataset.cases))) as pool:
        futures = {pool.submit(evaluator, case): index for index, case in enumerate(dataset.cases)}
        for future in as_completed(futures):
            ordered_results[futures[future]] = future.result()
    return [result for result in ordered_results if result is not None]


def _build_owner_add_report(dataset: DatasetSpec, case_results: list[OwnerAddCaseResult], toml_path: Path, cfg=None) -> dict[str, Any]:
    count_passes = sum(1 for result in case_results if result.count_pass)
    owner_passes = sum(1 for result in case_results if result.owner_pass)
    case_passes = sum(1 for result in case_results if result.case_pass)
    total_canonical_hits = sum(result.canonical_hits for result in case_results)
    total_canonical = sum(result.canonical_total for result in case_results)
    total_subject_hits = sum(result.subject_hits for result in case_results)
    total_subject = sum(result.subject_total for result in case_results)
    report = {
        "stage": "owner_add",
        "dataset": _display_path(dataset.path),
        "dataset_name": dataset.name,
        "toml_path": _display_path(toml_path),
        "total_cases": len(case_results),
        "targets": OWNER_ADD_TARGETS,
        "metrics": {
            "canonical_text_accuracy": _safe_ratio(total_canonical_hits, total_canonical),
            "subject_ref_accuracy": _safe_ratio(total_subject_hits, total_subject),
            "count_accuracy": _safe_ratio(count_passes, len(case_results)),
            "owner_accuracy": _safe_ratio(owner_passes, len(case_results)),
            "case_pass_rate": _safe_ratio(case_passes, len(case_results)),
        },
        "cases": [
            {
                "id": result.case_id,
                "description": result.description,
                "failures": result.failures,
                "active_memories": _json_ready(result.active_memories),
            }
            for result in case_results
        ],
    }
    if cfg is not None:
        models = {"default": f"{cfg.llm.provider}/{cfg.llm.model}"}
        for stage_name, stage_cfg in cfg.llm_stages.items():
            models[stage_name] = f"{stage_cfg.provider}/{stage_cfg.model}"
        report["models"] = models
    return report


def _build_stl_extract_report(dataset: DatasetSpec, case_results: list[StlExtractCaseResult], toml_path: Path, cfg=None) -> dict[str, Any]:
    case_passes = sum(1 for result in case_results if result.case_pass)
    total_ref_hits = sum(result.ref_hits for result in case_results)
    total_refs = sum(result.ref_total for result in case_results)
    total_statement_hits = sum(result.statement_hits for result in case_results)
    total_statements = sum(result.statement_total for result in case_results)
    total_strict_lines = sum(result.strict_lines for result in case_results)
    total_all_lines = sum(result.total_lines for result in case_results)
    report = {
        "stage": "stl_extract",
        "dataset": _display_path(dataset.path),
        "dataset_name": dataset.name,
        "toml_path": _display_path(toml_path),
        "total_cases": len(case_results),
        "targets": STL_EXTRACT_TARGETS,
        "metrics": {
            "ref_accuracy": _safe_ratio(total_ref_hits, total_refs),
            "statement_accuracy": _safe_ratio(total_statement_hits, total_statements),
            "stl_syntax_rate": _safe_ratio(total_strict_lines, total_all_lines),
            "case_pass_rate": _safe_ratio(case_passes, len(case_results)),
        },
        "cases": [
            {
                "id": result.case_id,
                "description": result.description,
                "failures": result.failures,
                "refs": _json_ready(result.refs),
                "statements": _json_ready(result.statements),
                "stl_text": result.stl_text,
                "expected_stl": result.expected_stl,
                "strict_lines": result.strict_lines,
                "total_lines": result.total_lines,
            }
            for result in case_results
        ],
    }
    if cfg is not None:
        models = {"default": f"{cfg.llm.provider}/{cfg.llm.model}"}
        for stage_name, stage_cfg in cfg.llm_stages.items():
            models[stage_name] = f"{stage_cfg.provider}/{stage_cfg.model}"
        report["models"] = models
    return report


def _build_summary(report: dict[str, Any], output_path: Path) -> str:
    metrics = report["metrics"]
    failed_metrics = [name for name, target in report["targets"].items() if metrics.get(name, 0.0) < target]
    failed_cases = [case for case in report["cases"] if case["failures"]]
    title = "Owner-Add Evaluation Summary" if report["stage"] == "owner_add" else "STL-Extract Evaluation Summary"
    lines = [
        title,
        f"stage: {report['stage']}",
        f"dataset: {report['dataset_name']} ({report['dataset']})",
        f"config: {report['toml_path']}",
    ]
    if "models" in report:
        models = report["models"]
        lines.append(f"model: {models.get('default', '?')}")
        for stage_name, value in models.items():
            if stage_name != "default":
                lines.append(f"  {stage_name}: {value}")
    lines.append(f"total cases: {report['total_cases']}")
    lines.append("metrics:")
    for name, target in report["targets"].items():
        value = metrics.get(name, 0.0)
        status = "PASS" if value >= target else "FAIL"
        lines.append(f"  - {name}: {value:.3f} (target {target:.2f}) [{status}]")
    lines.append("focus:")
    if failed_metrics:
        for name in failed_metrics:
            lines.append(f"  - improve {name}")
    else:
        lines.append("  - all configured metric targets passed")
    lines.append("failed cases:")
    if failed_cases:
        for case in failed_cases:
            lines.append(f"  - {case['id']}: {case['description']}")
            lines.append(f"    failures: {', '.join(case['failures'])}")
    else:
        lines.append("  - none")
    lines.append(f"json report saved to: {_display_path(output_path)}")
    return "\n".join(lines)


def _dataset_output_path(dataset_path: Path, output_arg: Path | None, stage: str, model_name: str = "") -> Path:
    model_suffix = f"_{_sanitize_name(model_name)}" if model_name else ""
    stage_suffix = f"_{stage}"
    base_name = dataset_path.name if dataset_path.is_dir() else dataset_path.stem
    file_name = f"{base_name}{stage_suffix}{model_suffix}_report.json"
    if output_arg is None:
        return DEFAULT_OUTPUT_DIR / file_name
    resolved = output_arg.resolve()
    if resolved.is_dir() or resolved.suffix != ".json":
        return resolved / file_name
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run unified staged evals against tests/eval/cases/.")
    parser.add_argument("--stage", choices=SUPPORTED_STAGES, required=True, help="Which eval stage to run.")
    parser.add_argument("--toml", type=Path, default=_DEFAULT_TEST_TOML, help="Path to config TOML (default: mindt.toml)")
    parser.add_argument("--case", type=Path, default=None, help="Single case JSON file or directory (default: tests/eval/cases/).")
    parser.add_argument("--output", type=Path, default=None, help="Output file or directory for the JSON report.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    parser.add_argument("--concurrency", type=int, default=1, help="Number of cases to evaluate in parallel. Default: 1.")
    parser.add_argument("--fail-on-targets", action="store_true", help="Return non-zero when any configured metric target fails.")
    parser.add_argument("--model", type=str, default=None, help="Override LLM model for all stages.")
    parser.add_argument("--provider", type=str, default=None, help="Override LLM provider for all stages.")
    args = parser.parse_args(argv)

    cfg = ConfigManager(toml_path=args.toml).get()
    if args.provider:
        cfg = ConfigManager(toml_path=args.toml).get(overrides={"llm": {"provider": args.provider}})
        cfg.llm.provider = args.provider
        for stage_cfg in cfg.llm_stages.values():
            stage_cfg.provider = args.provider
    if args.model:
        cfg.llm.model = args.model
        for stage_cfg in cfg.llm_stages.values():
            stage_cfg.model = args.model
    _configure_runner_logging(cfg)

    dataset_path = _resolve_dataset_path(args.case)
    dataset = _cases_for_stage(_load_dataset(dataset_path), args.stage)
    if not dataset.cases:
        sys.exit(f"Error: no cases under {_display_path(dataset_path)} support stage '{args.stage}'")

    if args.stage == "owner_add":
        case_results = _evaluate_cases(dataset, lambda case: _evaluate_owner_add_case(cfg, case), max(1, args.concurrency))
        report = _build_owner_add_report(dataset, case_results, args.toml, cfg=cfg)
    else:
        case_results = _evaluate_cases(dataset, lambda case: _evaluate_stl_extract_case(cfg, case), max(1, args.concurrency))
        report = _build_stl_extract_report(dataset, case_results, args.toml, cfg=cfg)

    output_path = _dataset_output_path(dataset_path, args.output, args.stage, model_name=cfg.llm.model)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None), encoding="utf-8")
    print(_build_summary(report, output_path))

    exit_code = 0
    if args.fail_on_targets:
        failed_metrics = [name for name, target in report["targets"].items() if report["metrics"].get(name, 0.0) < target]
        if failed_metrics:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
