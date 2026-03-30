from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mind.config import ConfigManager
from mind.llms.factory import LlmFactory
from mind.memory import Memory


DEFAULT_DATASET_DIR = PROJECT_ROOT / "tests" / "eval" / "datasets"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "tests" / "eval" / "reports"
TARGET_METRICS = {
    "recall": 0.90,
    "precision": 0.85,
    "no_extract_accuracy": 0.95,
    "confidence_accuracy": 0.70,
    "count_accuracy": 0.80,
}
RELATION_TARGET_METRICS = {
    "relation_recall": 0.90,
    "relation_forbidden_accuracy": 0.95,
    "relation_case_accuracy": 0.90,
}


@dataclass
class CaseResult:
    case_id: str
    description: str
    facts: list[dict[str, Any]]
    recall_hits: int
    recall_total: int
    precision_hits: int
    precision_total: int
    confidence_hits: int
    confidence_total: int
    relation_hits: int
    relation_total: int
    forbidden_relation_hits: int
    forbidden_relation_total: int
    relation_case_annotated: bool
    relation_case_pass: bool
    no_extract_pass: bool
    count_pass: bool
    case_pass: bool
    extracted_count: int
    expected_min_count: int
    expected_max_count: int
    missing_count: int
    forbidden_count: int
    confidence_failures: int
    failures: list[str]


@dataclass
class DatasetSpec:
    path: Path
    name: str
    focus: str
    description: str
    cases: list[dict[str, Any]]


def _configure_runner_logging(cfg) -> None:
    Memory._setup_logging(cfg.logging)


def _resolve_extraction_llm_cfg(cfg):
    return cfg.llm_stages.get("extraction", cfg.llm)


def _resolve_extraction_temperature(cfg) -> float | None:
    extraction_cfg = cfg.llm_stages.get("extraction")
    if extraction_cfg and extraction_cfg.extraction_temperature is not None:
        return extraction_cfg.extraction_temperature
    if extraction_cfg:
        return extraction_cfg.temperature
    return cfg.llm.extraction_temperature


def _expected_match_labels(expected: dict[str, Any]) -> list[str]:
    labels = expected.get("match_any")
    if isinstance(labels, list) and labels:
        return [str(label) for label in labels]
    label = expected.get("text_contains")
    return [str(label)] if label else []


def _load_dataset(dataset_path: Path) -> DatasetSpec:
    with dataset_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return DatasetSpec(
            path=dataset_path,
            name=dataset_path.stem,
            focus="general",
            description="",
            cases=payload,
        )
    if isinstance(payload, dict) and isinstance(payload.get("cases"), list):
        return DatasetSpec(
            path=dataset_path,
            name=str(payload.get("name", dataset_path.stem)),
            focus=str(payload.get("focus", "general")),
            description=str(payload.get("description", "")),
            cases=payload["cases"],
        )
    raise ValueError("extraction dataset must be a JSON list or an object with a 'cases' list")


def _resolve_dataset_paths(dataset_arg: Path | None) -> list[Path]:
    if dataset_arg is None:
        return sorted(DEFAULT_DATASET_DIR.glob("extraction*_cases.json"))

    resolved = dataset_arg.resolve()
    if resolved.is_dir():
        return sorted(resolved.glob("extraction*_cases.json"))
    return [resolved]


def _contains_case_insensitive(text: str, needle: str) -> bool:
    return needle.casefold() in text.casefold()


def _relation_labels(expectation: dict[str, Any]) -> list[str]:
    labels = expectation.get("match_all")
    if isinstance(labels, list) and labels:
        return [str(label) for label in labels]
    labels = expectation.get("match_any")
    if isinstance(labels, list) and labels:
        return [str(label) for label in labels]
    label = expectation.get("label")
    return [str(label)] if label else []


def _relation_matches(text: str, expectation: dict[str, Any]) -> bool:
    match_all = expectation.get("match_all", [])
    if match_all and not all(
        _contains_case_insensitive(text, str(label))
        for label in match_all
    ):
        return False

    match_any = expectation.get("match_any", [])
    if match_any and not any(
        _contains_case_insensitive(text, str(label))
        for label in match_any
    ):
        return False

    return bool(match_all or match_any)


def _evaluate_case(llm, case: dict[str, Any], extraction_temperature: float | None) -> CaseResult:
    facts = Memory._extract_facts(
        llm,
        case["input"],
        temperature=extraction_temperature,
    )
    fact_texts = [fact.get("text", "") for fact in facts]
    failures: list[str] = []

    expected_facts = case.get("expected_facts", [])
    expected_relations = case.get("expected_relations", [])
    forbidden_relations = case.get("forbidden_relations", [])
    recall_hits = 0
    confidence_hits = 0
    confidence_total = 0
    relation_hits = 0
    forbidden_relation_hits = 0
    missing_count = 0
    confidence_failures = 0
    for expected in expected_facts:
        matched = None
        match_labels = _expected_match_labels(expected)
        for fact in facts:
            if any(
                _contains_case_insensitive(fact.get("text", ""), label)
                for label in match_labels
            ):
                matched = fact
                break
        if matched is None:
            failures.append(f"missing:{' | '.join(match_labels)}")
            missing_count += 1
            continue

        recall_hits += 1
        confidence_range = expected.get("confidence_range")
        if confidence_range is not None:
            confidence_total += 1
            confidence = matched.get("confidence", 0.0)
            if confidence_range[0] <= confidence <= confidence_range[1]:
                confidence_hits += 1
            else:
                confidence_failures += 1
                failures.append(
                    f"confidence:{' | '.join(match_labels)}={confidence} not in {confidence_range}"
                )

    relation_failures = 0
    for expected in expected_relations:
        matched = next(
            (
                fact for fact in facts
                if _relation_matches(fact.get("text", ""), expected)
            ),
            None,
        )
        if matched is None:
            relation_failures += 1
            failures.append(
                f"missing_relation:{' | '.join(_relation_labels(expected))}"
            )
            continue
        relation_hits += 1

    for expected in forbidden_relations:
        matched = next(
            (
                fact for fact in facts
                if _relation_matches(fact.get("text", ""), expected)
            ),
            None,
        )
        if matched is not None:
            relation_failures += 1
            failures.append(
                f"forbidden_relation:{matched.get('text', '')}"
            )
            continue
        forbidden_relation_hits += 1

    should_not_extract = case.get("should_not_extract", [])
    precision_hits = 0
    forbidden_count = 0
    for fact_text in fact_texts:
        if any(_contains_case_insensitive(fact_text, needle) for needle in should_not_extract):
            failures.append(f"forbidden:{fact_text}")
            forbidden_count += 1
            continue
        precision_hits += 1

    expected_count_range = case.get("expected_count_range", [0, len(facts)])
    expected_min_count = expected_count_range[0]
    expected_max_count = expected_count_range[1]
    zero_extract_expected = not expected_facts and expected_count_range == [0, 0]
    relation_case_annotated = bool(expected_relations or forbidden_relations)
    relation_case_pass = relation_case_annotated and relation_failures == 0
    no_extract_pass = not facts if zero_extract_expected else True
    count_pass = expected_min_count <= len(facts) <= expected_max_count
    if not count_pass:
        failures.append(
            f"count:{len(facts)} not in [{expected_min_count}, {expected_max_count}]"
        )

    return CaseResult(
        case_id=case["id"],
        description=case.get("description", ""),
        facts=facts,
        recall_hits=recall_hits,
        recall_total=len(expected_facts),
        precision_hits=precision_hits,
        precision_total=len(facts),
        confidence_hits=confidence_hits,
        confidence_total=confidence_total,
        relation_hits=relation_hits,
        relation_total=len(expected_relations),
        forbidden_relation_hits=forbidden_relation_hits,
        forbidden_relation_total=len(forbidden_relations),
        relation_case_annotated=relation_case_annotated,
        relation_case_pass=relation_case_pass,
        no_extract_pass=no_extract_pass,
        count_pass=count_pass,
        case_pass=not failures,
        extracted_count=len(facts),
        expected_min_count=expected_min_count,
        expected_max_count=expected_max_count,
        missing_count=missing_count,
        forbidden_count=forbidden_count,
        confidence_failures=confidence_failures,
        failures=failures,
    )


def _safe_ratio(numerator: int, denominator: int, empty_value: float = 1.0) -> float:
    if denominator == 0:
        return empty_value
    return numerator / denominator


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


def _llm_descriptor(llm_cfg) -> dict[str, str]:
    provider = str(getattr(llm_cfg, "provider", "unknown"))
    model = str(getattr(llm_cfg, "model", "unknown"))
    label = re.sub(r"[^a-z0-9._-]+", "-", f"{provider}-{model}".lower()).strip("-")
    return {
        "provider": provider,
        "model": model,
        "label": label or "unknown-llm",
    }


def build_report(
    dataset: DatasetSpec,
    case_results: list[CaseResult],
    toml_path: Path,
    llm_info: dict[str, str],
) -> dict[str, Any]:
    total_recall_hits = sum(result.recall_hits for result in case_results)
    total_recall = sum(result.recall_total for result in case_results)
    total_precision_hits = sum(result.precision_hits for result in case_results)
    total_precision = sum(result.precision_total for result in case_results)
    total_confidence_hits = sum(result.confidence_hits for result in case_results)
    total_confidence = sum(result.confidence_total for result in case_results)
    total_relation_hits = sum(result.relation_hits for result in case_results)
    total_relations = sum(result.relation_total for result in case_results)
    total_forbidden_relation_hits = sum(result.forbidden_relation_hits for result in case_results)
    total_forbidden_relations = sum(result.forbidden_relation_total for result in case_results)
    relation_cases = [result for result in case_results if result.relation_case_annotated]
    relation_case_passes = sum(1 for result in relation_cases if result.relation_case_pass)
    no_extract_cases = [
        result for result in case_results
        if result.expected_min_count == 0 and result.expected_max_count == 0
    ]
    no_extract_passes = sum(1 for result in no_extract_cases if result.no_extract_pass)
    count_passes = sum(1 for result in case_results if result.count_pass)
    case_passes = sum(1 for result in case_results if result.case_pass)
    missing_total = sum(result.missing_count for result in case_results)
    forbidden_total = sum(result.forbidden_count for result in case_results)
    confidence_fail_total = sum(result.confidence_failures for result in case_results)
    under_count_cases = sum(
        1 for result in case_results if result.extracted_count < result.expected_min_count
    )
    over_count_cases = sum(
        1 for result in case_results if result.extracted_count > result.expected_max_count
    )
    total_extracted = sum(result.extracted_count for result in case_results)
    empty_expected_extracted = sum(result.extracted_count for result in no_extract_cases)

    failure_breakdown = {
        "missing": missing_total,
        "forbidden": forbidden_total,
        "confidence": confidence_fail_total,
        "count": sum(1 for result in case_results if not result.count_pass),
    }
    targets = dict(TARGET_METRICS)
    metrics = {
        "recall": _safe_ratio(total_recall_hits, total_recall),
        "precision": _safe_ratio(total_precision_hits, total_precision),
        "no_extract_accuracy": _safe_ratio(no_extract_passes, len(no_extract_cases)),
        "confidence_accuracy": _safe_ratio(total_confidence_hits, total_confidence),
        "count_accuracy": _safe_ratio(count_passes, len(case_results)),
        "case_pass_rate": _safe_ratio(case_passes, len(case_results)),
        "missing_expectation_rate": _safe_ratio(missing_total, total_recall, empty_value=0.0),
        "forbidden_case_rate": _safe_ratio(
            sum(1 for result in case_results if result.forbidden_count > 0),
            len(case_results),
        ),
        "under_count_rate": _safe_ratio(under_count_cases, len(case_results)),
        "over_count_rate": _safe_ratio(over_count_cases, len(case_results)),
        "avg_extracted_facts": _safe_ratio(total_extracted, len(case_results)),
        "avg_extracted_facts_on_empty_cases": _safe_ratio(
            empty_expected_extracted,
            len(no_extract_cases),
            empty_value=0.0,
        ),
    }
    if relation_cases:
        targets.update(RELATION_TARGET_METRICS)
        failure_breakdown["relation_missing"] = total_relations - total_relation_hits
        failure_breakdown["relation_forbidden"] = (
            total_forbidden_relations - total_forbidden_relation_hits
        )
        metrics.update(
            {
                "relation_recall": _safe_ratio(total_relation_hits, total_relations),
                "relation_forbidden_accuracy": _safe_ratio(
                    total_forbidden_relation_hits,
                    total_forbidden_relations,
                ),
                "relation_case_accuracy": _safe_ratio(
                    relation_case_passes,
                    len(relation_cases),
                ),
            }
        )

    return {
        "dataset": _display_path(dataset.path),
        "dataset_name": dataset.name,
        "dataset_focus": dataset.focus,
        "dataset_description": dataset.description,
        "toml_path": _display_path(toml_path),
        "llm": llm_info,
        "total_cases": len(case_results),
        "targets": targets,
        "metrics": metrics,
        "failure_breakdown": failure_breakdown,
        "cases": [
            {
                "id": result.case_id,
                "description": result.description,
                "facts": result.facts,
                "relation_case_annotated": result.relation_case_annotated,
                "failures": result.failures,
            }
            for result in case_results
        ],
    }


def _dataset_output_path(
    dataset_path: Path,
    output_arg: Path | None,
    multi_dataset: bool,
    llm_label: str,
) -> Path:
    file_name = f"{dataset_path.stem}_{llm_label}_report.json"
    if output_arg is None:
        return DEFAULT_OUTPUT_DIR / file_name

    resolved = output_arg.resolve()
    if multi_dataset or resolved.is_dir() or resolved.suffix != ".json":
        return resolved / file_name
    return resolved


def build_summary(report: dict[str, Any], output_path: Path) -> str:
    metrics = report["metrics"]
    targets = report["targets"]
    failed_metrics = [
        name
        for name, target in targets.items()
        if metrics.get(name, 0.0) < target
    ]
    failed_cases = [case for case in report["cases"] if case["failures"]]
    failure_breakdown = report["failure_breakdown"]

    lines = [
        "Extraction Evaluation Summary",
        f"dataset: {report['dataset_name']} ({report['dataset']})",
        f"focus: {report['dataset_focus']}",
        f"config: {report['toml_path']}",
        f"llm: {report['llm']['provider']} / {report['llm']['model']}",
        f"total cases: {report['total_cases']}",
        "metrics:",
    ]
    for name, target in targets.items():
        value = metrics.get(name, 0.0)
        status = "PASS" if value >= target else "FAIL"
        lines.append(f"  - {name}: {value:.3f} (target {target:.2f}) [{status}]")

    if failed_metrics:
        lines.append("focus:")
        for name in failed_metrics:
            lines.append(f"  - improve {name}")
    else:
        lines.append("focus:")
        lines.append("  - all configured metric targets passed")

    lines.append("diagnostics:")
    lines.append(f"  - case_pass_rate: {metrics['case_pass_rate']:.3f}")
    lines.append(f"  - missing_expectation_rate: {metrics['missing_expectation_rate']:.3f}")
    lines.append(f"  - forbidden_case_rate: {metrics['forbidden_case_rate']:.3f}")
    lines.append(f"  - under_count_rate: {metrics['under_count_rate']:.3f}")
    lines.append(f"  - over_count_rate: {metrics['over_count_rate']:.3f}")
    lines.append(f"  - avg_extracted_facts: {metrics['avg_extracted_facts']:.3f}")
    lines.append(
        "  - avg_extracted_facts_on_empty_cases: "
        f"{metrics['avg_extracted_facts_on_empty_cases']:.3f}"
    )
    lines.append(
        "failure breakdown: "
        f"missing={failure_breakdown['missing']}, "
        f"forbidden={failure_breakdown['forbidden']}, "
        f"confidence={failure_breakdown['confidence']}, "
        f"count={failure_breakdown['count']}"
    )
    if "relation_missing" in failure_breakdown or "relation_forbidden" in failure_breakdown:
        lines.append(
            "relation breakdown: "
            f"missing={failure_breakdown.get('relation_missing', 0)}, "
            f"forbidden={failure_breakdown.get('relation_forbidden', 0)}"
        )

    if failed_cases:
        lines.append("failed cases:")
        for case in failed_cases:
            lines.append(f"  - {case['id']}: {case['description']}")
            lines.append(f"    failures: {', '.join(case['failures'])}")
            if case["facts"]:
                fact_texts = [fact.get("text", "") for fact in case["facts"]]
                lines.append(f"    extracted: {'; '.join(fact_texts)}")
            else:
                lines.append("    extracted: <empty>")
    else:
        lines.append("failed cases:")
        lines.append("  - none")

    lines.append(f"json report saved to: {_display_path(output_path)}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run extraction evaluation cases.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Path to a dataset file or a dataset directory. Omit to run all extraction datasets.",
    )
    parser.add_argument(
        "--toml",
        type=Path,
        default=PROJECT_ROOT / "mindt.toml",
        help="TOML config path used to build the LLM client",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the JSON report",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the JSON report to stdout after the human summary",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Print only JSON to stdout (for scripts), without the human summary",
    )
    parser.add_argument(
        "--fail-on-targets",
        action="store_true",
        help="Exit with code 1 when any configured metric target is not met",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of parallel workers for case evaluation (default: 1 = sequential)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    toml_path = args.toml.resolve()
    dataset_paths = _resolve_dataset_paths(args.dataset)
    if not dataset_paths:
        raise ValueError("No extraction datasets found")

    cfg = ConfigManager(toml_path=toml_path).get()
    _configure_runner_logging(cfg)
    extraction_llm_cfg = _resolve_extraction_llm_cfg(cfg)
    extraction_temperature = _resolve_extraction_temperature(cfg)
    llm = LlmFactory.create(extraction_llm_cfg)
    llm_info = _llm_descriptor(extraction_llm_cfg)

    concurrency = max(1, args.concurrency)
    reports: list[dict[str, Any]] = []
    summaries: list[str] = []
    multi_dataset = len(dataset_paths) > 1
    for dataset_path in dataset_paths:
        dataset = _load_dataset(dataset_path)
        if concurrency <= 1:
            case_results = [
                _evaluate_case(llm, case, extraction_temperature)
                for case in dataset.cases
            ]
        else:
            case_results: list[CaseResult] = [None] * len(dataset.cases)  # type: ignore[list-item]
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                future_to_idx = {
                    pool.submit(_evaluate_case, llm, case, extraction_temperature): idx
                    for idx, case in enumerate(dataset.cases)
                }
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    case_results[idx] = future.result()
        report = build_report(dataset, case_results, toml_path, llm_info)
        output_path = _dataset_output_path(
            dataset.path,
            args.output,
            multi_dataset,
            llm_info["label"],
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        reports.append(report)
        summaries.append(build_summary(report, output_path))

    if args.json_only:
        payload: Any = reports[0] if len(reports) == 1 else {"reports": reports}
        print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
    else:
        for index, summary in enumerate(summaries):
            if index > 0:
                print()
            print(summary)
            if args.pretty:
                print()
                print(json.dumps(reports[index], ensure_ascii=False, indent=2))

    if args.fail_on_targets and any(
        any(report["metrics"].get(name, 0.0) < target for name, target in report["targets"].items())
        for report in reports
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
