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
from mind.memory import Memory


DEFAULT_DATASET_DIR = PROJECT_ROOT / "tests" / "eval" / "datasets"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "tests" / "eval" / "reports"
TARGET_METRICS = {
    "canonical_text_accuracy": 0.95,
    "subject_ref_accuracy": 0.95,
    "count_accuracy": 0.95,
    "owner_accuracy": 1.00,
    "ref_accuracy": 0.90,
    "statement_accuracy": 0.90,
    "evidence_accuracy": 0.90,
    "update_accuracy": 0.90,
}


@dataclass
class DatasetSpec:
    path: Path
    name: str
    focus: str
    description: str
    cases: list[dict[str, Any]]


@dataclass
class CaseResult:
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
    ref_hits: int
    ref_total: int
    statement_hits: int
    statement_total: int
    evidence_hits: int
    evidence_total: int
    update_hits: int
    update_total: int
    case_pass: bool
    failures: list[str]
    active_memories: list[dict[str, Any]]
    current_statements: list[dict[str, Any]]
    refs: list[dict[str, Any]]
    evidence: list[dict[str, Any]]


def _configure_runner_logging(cfg) -> None:
    Memory._setup_logging(cfg.logging)


def _load_dataset(dataset_path: Path) -> DatasetSpec:
    with dataset_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return DatasetSpec(
        path=dataset_path,
        name=str(payload.get("name", dataset_path.stem)),
        focus=str(payload.get("focus", "owner-centered add")),
        description=str(payload.get("description", "")),
        cases=list(payload.get("cases", [])),
    )


def _resolve_dataset_paths(dataset_arg: Path | None) -> list[Path]:
    if dataset_arg is None:
        return sorted(DEFAULT_DATASET_DIR.glob("owner_centered*_cases.json"))

    resolved = dataset_arg.resolve()
    if resolved.is_dir():
        return sorted(resolved.glob("owner_centered*_cases.json"))
    return [resolved]


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


def _case_owner_context(case: dict[str, Any]) -> OwnerContext:
    owner = case.get("owner", {})
    return OwnerContext(**owner)


def _case_owner_lookup(case: dict[str, Any]) -> str:
    owner = case.get("owner", {})
    return (
        owner.get("external_user_id")
        or owner.get("anonymous_session_id")
        or ""
    )


def _sanitize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", value.casefold()).strip("-") or "case"


def _eval_config(cfg, case_id: str, temp_dir: str):
    eval_cfg = cfg.model_copy(deep=True)
    eval_cfg.vector_store.collection_name = f"eval_{_sanitize_name(case_id)}"
    eval_cfg.vector_store.url = ""
    eval_cfg.vector_store.api_key = ""
    eval_cfg.history_store.provider = "sqlite"
    eval_cfg.history_store.db_path = str(Path(temp_dir) / "history.db")
    eval_cfg.stl_store.provider = "sqlite"
    eval_cfg.stl_store.db_path = str(Path(temp_dir) / "stl.db")
    eval_cfg.logging.console = False
    eval_cfg.logging.file = ""
    return eval_cfg


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


def _stored_evidence_rows(memory: Memory, owner_id: str) -> list[dict[str, Any]]:
    conn = memory._stl_store._get_conn()
    rows = conn.execute(
        """
        SELECT e.target_id, e.conf, e.src, e.span, e.residual, s.predicate
        FROM evidence e
        JOIN statements s ON s.id = e.target_id
        WHERE s.owner_id = ? AND s.is_current = 1
        ORDER BY e.target_id
        """,
        (owner_id,),
    ).fetchall()
    return [dict(row) for row in rows]


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
        return f'@{row["scope"]}/{ref_type}("{key}")'
    return arg


def _statement_matches(row: dict[str, Any], expectation: dict[str, Any], refs_by_id: dict[str, dict[str, Any]]) -> bool:
    if expectation.get("predicate") and row.get("predicate") != expectation["predicate"]:
        return False
    if expectation.get("category") and row.get("category") != expectation["category"]:
        return False

    rendered_args = [_render_stored_arg(arg, refs_by_id) for arg in row.get("args", [])]
    if "args" in expectation and rendered_args != expectation["args"]:
        return False

    flat_args = json.dumps(rendered_args, ensure_ascii=False)
    args_contains = expectation.get("args_contains", [])
    if args_contains and not all(str(label) in flat_args for label in args_contains):
        return False

    return True


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
    if expectation.get("versioned") is True and not item.version_of:
        return False
    return True


def _ref_matches(row: dict[str, Any], expectation: dict[str, Any]) -> bool:
    for key in ("scope", "ref_type", "key"):
        if key in expectation and row.get(key) != expectation[key]:
            return False
    return True


def _evidence_matches(row: dict[str, Any], expectation: dict[str, Any]) -> bool:
    if expectation.get("predicate") and row.get("predicate") != expectation["predicate"]:
        return False
    if expectation.get("src") and row.get("src") != expectation["src"]:
        return False
    if expectation.get("span_contains") and expectation["span_contains"] not in (row.get("span") or ""):
        return False
    conf_range = expectation.get("conf_range")
    if conf_range is not None and not (conf_range[0] <= row.get("conf", 0.0) <= conf_range[1]):
        return False
    return True


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


def _evaluate_case(cfg, case: dict[str, Any]) -> CaseResult:
    failures: list[str] = []
    owner_context = _case_owner_context(case)
    owner_lookup = _case_owner_lookup(case)

    with tempfile.TemporaryDirectory(prefix=f"owner_eval_{_sanitize_name(case['id'])}_") as temp_dir:
        eval_cfg = _eval_config(cfg, case["id"], temp_dir)
        memory = Memory(eval_cfg)
        try:
            for turn in case.get("turns", []):
                memory.add(
                    messages=turn.get("messages", []),
                    owner=owner_context,
                    session_id=turn.get("session_id"),
                    metadata=turn.get("metadata"),
                )

            owner_record = memory._history_store.resolve_owner(owner_context)
            active_memories = memory.get_all(owner_lookup, limit=500)
            deleted_rows = memory._vector_store.list(
                filters={"user_id": owner_lookup, "status": "deleted"},
                limit=500,
            )
            deleted_memories = [
                memory._payload_to_item(row["id"], row.get("payload", {}))
                for row in deleted_rows
            ]
            current_statements = memory._stl_store.query_statements(
                owner_id=owner_record.owner_id,
                is_current=True,
                limit=500,
            )
            refs = _stored_ref_rows(memory, owner_record.owner_id)
            evidence = _stored_evidence_rows(memory, owner_record.owner_id)
        finally:
            memory.close()

    owner_pass = all(item.owner_id == owner_record.owner_id for item in active_memories)
    if not owner_pass:
        failures.append("owner:mismatch")

    expected_active_count = case.get("expected_active_count")
    count_pass = True
    if expected_active_count is not None:
        count_pass = len(active_memories) == expected_active_count
        if not count_pass:
            failures.append(f"count:{len(active_memories)} != {expected_active_count}")

    canonical_hits = 0
    canonical_total = 0
    subject_hits = 0
    subject_total = 0
    active_expectations = case.get("expected_active_memories", [])
    for expected in active_expectations:
        matched = next((item for item in active_memories if _memory_matches(item, expected)), None)
        if matched is None:
            failures.append(f"missing_active:{expected.get('canonical_text') or expected.get('canonical_text_contains') or expected}")
            continue
        if "canonical_text" in expected or "canonical_text_contains" in expected:
            canonical_hits += 1
            canonical_total += 1
        if "subject_ref" in expected:
            subject_hits += 1
            subject_total += 1

    ref_hits = 0
    ref_total = 0
    for expected in case.get("expected_refs", []):
        ref_total += 1
        if any(_ref_matches(row, expected) for row in refs):
            ref_hits += 1
        else:
            failures.append(f"missing_ref:{expected}")

    refs_by_id = {row["id"]: row for row in refs}
    statement_hits = 0
    statement_total = 0
    for expected in case.get("expected_statements", []):
        statement_total += 1
        if any(_statement_matches(row, expected, refs_by_id) for row in current_statements):
            statement_hits += 1
        else:
            failures.append(f"missing_statement:{expected}")

    evidence_hits = 0
    evidence_total = 0
    for expected in case.get("expected_evidence", []):
        evidence_total += 1
        if any(_evidence_matches(row, expected) for row in evidence):
            evidence_hits += 1
        else:
            failures.append(f"missing_evidence:{expected}")

    update_hits = 0
    update_total = 0
    for expected in case.get("expected_deleted_memories", []):
        update_total += 1
        if any(_memory_matches(item, expected) for item in deleted_memories):
            update_hits += 1
        else:
            failures.append(f"missing_deleted:{expected}")

    versioned_memories = [item for item in active_memories if item.version_of]
    for expected in case.get("expected_versioned_active_memories", []):
        update_total += 1
        if any(_memory_matches(item, {**expected, "versioned": True}) for item in versioned_memories):
            update_hits += 1
        else:
            failures.append(f"missing_versioned:{expected}")

    case_pass = not failures
    return CaseResult(
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
        ref_hits=ref_hits,
        ref_total=ref_total,
        statement_hits=statement_hits,
        statement_total=statement_total,
        evidence_hits=evidence_hits,
        evidence_total=evidence_total,
        update_hits=update_hits,
        update_total=update_total,
        case_pass=case_pass,
        failures=failures,
        active_memories=[_serialize_item(item) for item in active_memories],
        current_statements=current_statements,
        refs=refs,
        evidence=evidence,
    )


def _evaluate_dataset_cases(cfg, dataset: DatasetSpec, concurrency: int = 1) -> list[CaseResult]:
    if concurrency <= 1 or len(dataset.cases) <= 1:
        return [_evaluate_case(cfg, case) for case in dataset.cases]

    ordered_results: list[CaseResult | None] = [None] * len(dataset.cases)
    max_workers = min(concurrency, len(dataset.cases))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_evaluate_case, cfg, case): index
            for index, case in enumerate(dataset.cases)
        }
        for future in as_completed(futures):
            ordered_results[futures[future]] = future.result()

    return [result for result in ordered_results if result is not None]


def build_report(
    dataset: DatasetSpec,
    case_results: list[CaseResult],
    toml_path: Path,
) -> dict[str, Any]:
    count_passes = sum(1 for result in case_results if result.count_pass)
    owner_passes = sum(1 for result in case_results if result.owner_pass)
    case_passes = sum(1 for result in case_results if result.case_pass)

    total_canonical_hits = sum(result.canonical_hits for result in case_results)
    total_canonical = sum(result.canonical_total for result in case_results)
    total_subject_hits = sum(result.subject_hits for result in case_results)
    total_subject = sum(result.subject_total for result in case_results)
    total_ref_hits = sum(result.ref_hits for result in case_results)
    total_refs = sum(result.ref_total for result in case_results)
    total_statement_hits = sum(result.statement_hits for result in case_results)
    total_statements = sum(result.statement_total for result in case_results)
    total_evidence_hits = sum(result.evidence_hits for result in case_results)
    total_evidence = sum(result.evidence_total for result in case_results)
    total_update_hits = sum(result.update_hits for result in case_results)
    total_updates = sum(result.update_total for result in case_results)

    metrics = {
        "canonical_text_accuracy": _safe_ratio(total_canonical_hits, total_canonical),
        "subject_ref_accuracy": _safe_ratio(total_subject_hits, total_subject),
        "count_accuracy": _safe_ratio(count_passes, len(case_results)),
        "owner_accuracy": _safe_ratio(owner_passes, len(case_results)),
        "ref_accuracy": _safe_ratio(total_ref_hits, total_refs),
        "statement_accuracy": _safe_ratio(total_statement_hits, total_statements),
        "evidence_accuracy": _safe_ratio(total_evidence_hits, total_evidence),
        "update_accuracy": _safe_ratio(total_update_hits, total_updates),
        "case_pass_rate": _safe_ratio(case_passes, len(case_results)),
    }

    return {
        "dataset": _display_path(dataset.path),
        "dataset_name": dataset.name,
        "dataset_focus": dataset.focus,
        "dataset_description": dataset.description,
        "toml_path": _display_path(toml_path),
        "total_cases": len(case_results),
        "targets": TARGET_METRICS,
        "metrics": metrics,
        "cases": [
            {
                "id": result.case_id,
                "description": result.description,
                "failures": result.failures,
                "active_memories": _json_ready(result.active_memories),
                "current_statements": _json_ready(result.current_statements),
                "refs": _json_ready(result.refs),
                "evidence": _json_ready(result.evidence),
            }
            for result in case_results
        ],
    }


def build_summary(report: dict[str, Any], output_path: Path) -> str:
    metrics = report["metrics"]
    failed_metrics = [
        name for name, target in report["targets"].items()
        if metrics.get(name, 0.0) < target
    ]
    failed_cases = [case for case in report["cases"] if case["failures"]]

    lines = [
        "Owner-Centered Add Evaluation Summary",
        f"dataset: {report['dataset_name']} ({report['dataset']})",
        f"focus: {report['dataset_focus']}",
        f"config: {report['toml_path']}",
        f"total cases: {report['total_cases']}",
        "metrics:",
    ]
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

    lines.append(f"diagnostics:")
    lines.append(f"  - case_pass_rate: {metrics['case_pass_rate']:.3f}")
    lines.append(f"failed cases:")
    if failed_cases:
        for case in failed_cases:
            lines.append(f"  - {case['id']}: {case['description']}")
            lines.append(f"    failures: {', '.join(case['failures'])}")
    else:
        lines.append("  - none")

    lines.append(f"json report saved to: {_display_path(output_path)}")
    return "\n".join(lines)


def _dataset_output_path(dataset_path: Path, output_arg: Path | None, multi_dataset: bool) -> Path:
    file_name = f"{dataset_path.stem}_report.json"
    if output_arg is None:
        return DEFAULT_OUTPUT_DIR / file_name

    resolved = output_arg.resolve()
    if multi_dataset or resolved.is_dir() or resolved.suffix != ".json":
        return resolved / file_name
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the STL-native owner-centered Memory.add() pipeline.")
    parser.add_argument(
        "--toml",
        type=Path,
        default=_DEFAULT_TEST_TOML,
        help="Path to config TOML (default: mindt.toml)",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Dataset JSON path or directory. Defaults to all owner_centered*_cases.json files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file or directory for the JSON report.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of cases to evaluate in parallel. Default: 1.",
    )
    parser.add_argument(
        "--fail-on-targets",
        action="store_true",
        help="Return non-zero when any configured metric target fails.",
    )
    args = parser.parse_args(argv)

    cfg = ConfigManager(toml_path=args.toml).get()
    _configure_runner_logging(cfg)

    dataset_paths = _resolve_dataset_paths(args.dataset)
    multi_dataset = len(dataset_paths) > 1
    exit_code = 0

    for dataset_path in dataset_paths:
        dataset = _load_dataset(dataset_path)
        case_results = _evaluate_dataset_cases(
            cfg,
            dataset,
            concurrency=max(1, args.concurrency),
        )
        report = build_report(dataset, case_results, args.toml)
        output_path = _dataset_output_path(dataset_path, args.output, multi_dataset)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None),
            encoding="utf-8",
        )
        print(build_summary(report, output_path))

        if args.fail_on_targets:
            failed_metrics = [
                name for name, target in report["targets"].items()
                if report["metrics"].get(name, 0.0) < target
            ]
            if failed_metrics:
                exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
