"""Prompt optimization benchmark runner.

Runs STL extraction across multiple models, evaluates quality using an
LLM-as-judge, measures latency, and produces a comparative report.

Usage examples:

  # Run all cases against two models, judge with gpt-5.4-nano:
  python tests/eval/prompt_opt/runner.py \\
    --toml mindt.toml \\
    --models aapi:gpt-5.4-nano leihuo:deepseek-v3.2 \\
    --judge aapi:gpt-5.4-nano

  # Single case, three models (opus as baseline):
  python tests/eval/prompt_opt/runner.py \\
    --toml mindt.toml \\
    --models aapi:claude-opus-4-6 aapi:gpt-5.4-nano leihuo:deepseek-v3.2 \\
    --judge aapi:gpt-5.4-nano \\
    --case tests/eval/prompt_opt/cases/po-correction-001.json

  # Pretty-print and save report:
  python tests/eval/prompt_opt/runner.py \\
    --toml mindt.toml \\
    --models leihuo:deepseek-v3.2 aapi:gpt-5.4-nano \\
    --judge aapi:gpt-5.4-nano \\
    --pretty
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mind.config import ConfigManager
from mind.config.manager import _DEFAULT_TEST_TOML
from mind.llms.factory import LlmFactory
from mind.runtime_logging import configure_runtime_logging
from mind.stl.prompt import (
    STL_EXTRACTION_SYSTEM_PROMPT,
    STL_EXTRACTION_USER_TEMPLATE,
    format_focus_stack,
)
from mind.utils import parse_messages
from tests.eval.prompt_opt.judge import (
    DIMENSIONS,
    DIMENSION_WEIGHTS,
    DimensionScore,
    JudgeResult,
    evaluate as judge_evaluate,
)

DEFAULT_CASES_DIR = Path(__file__).resolve().parent / "cases"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "tests" / "eval" / "reports"

# ── Data structures ──────────────────────────────────────────────────


@dataclass
class ExtractionResult:
    model: str
    provider: str
    stl_text: str
    latency_ms: float


@dataclass
class CaseModelResult:
    case_id: str
    model: str
    provider: str
    stl_text: str
    latency_ms: float
    judge: JudgeResult


@dataclass
class CaseSummary:
    case_id: str
    description: str
    category: str
    results_by_model: dict[str, CaseModelResult] = field(default_factory=dict)


# ── Helpers ──────────────────────────────────────────────────────────


def _parse_model_spec(spec: str) -> tuple[str, str]:
    """Parse 'provider:model' string. Returns (provider, model)."""
    if ":" in spec:
        provider, model = spec.split(":", 1)
        return provider.strip(), model.strip()
    # If no provider prefix, assume aapi
    return "aapi", spec.strip()


def _load_case(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_cases(source: Path) -> list[dict[str, Any]]:
    resolved = source.resolve()
    if resolved.is_dir():
        files = sorted(resolved.glob("*.json"))
        return [_load_case(p) for p in files]
    return [_load_case(resolved)]


def _case_conversation(case: dict[str, Any]) -> str:
    messages: list[dict[str, str]] = []
    for turn in case.get("turns", []):
        messages.extend(turn.get("messages", []))
    return parse_messages(messages)


def _build_stl_messages(conversation: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": STL_EXTRACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": STL_EXTRACTION_USER_TEMPLATE.format(
                focus_stack=format_focus_stack([]),
                conversation=conversation,
            ),
        },
    ]


def _create_llm(cfg_mgr: ConfigManager, provider: str, model: str):
    """Create an LLM instance for a specific provider:model pair."""
    resolved = cfg_mgr.get(overrides={"llm": {"provider": provider}})
    resolved.llm.provider = provider
    resolved.llm.model = model
    return LlmFactory.create(resolved.llm)


# ── Core evaluation ──────────────────────────────────────────────────


def _extract_stl(llm, conversation: str) -> ExtractionResult:
    """Run STL extraction and measure latency."""
    messages = _build_stl_messages(conversation)
    t0 = time.perf_counter()
    stl_text = llm.generate(messages=messages, temperature=0.0)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    return ExtractionResult(
        model=getattr(llm, "model", "?"),
        provider=getattr(llm, "provider", "?"),
        stl_text=stl_text,
        latency_ms=round(elapsed_ms, 1),
    )


def _evaluate_case(
    case: dict[str, Any],
    model_specs: list[tuple[str, str]],
    llm_instances: dict[str, Any],
    judge_llm: Any,
) -> CaseSummary:
    """Evaluate one case across all models."""
    case_id = case["id"]
    conversation = _case_conversation(case)
    golden_stl = case.get("golden_stl", "")

    summary = CaseSummary(
        case_id=case_id,
        description=case.get("description", ""),
        category=case.get("category", ""),
    )

    for provider, model in model_specs:
        key = f"{provider}:{model}"
        llm = llm_instances[key]

        # Step 1: Extract STL
        extraction = _extract_stl(llm, conversation)

        # Step 2: Judge quality
        judge_result = judge_evaluate(
            judge_llm=judge_llm,
            conversation=conversation,
            golden_stl=golden_stl,
            actual_stl=extraction.stl_text,
        )

        summary.results_by_model[key] = CaseModelResult(
            case_id=case_id,
            model=model,
            provider=provider,
            stl_text=extraction.stl_text,
            latency_ms=extraction.latency_ms,
            judge=judge_result,
        )

    return summary


# ── Report building ──────────────────────────────────────────────────


def _build_report(
    summaries: list[CaseSummary],
    model_specs: list[tuple[str, str]],
    judge_spec: str,
) -> dict[str, Any]:
    """Build the full JSON report."""
    model_keys = [f"{p}:{m}" for p, m in model_specs]

    # Per-model aggregates
    model_agg: dict[str, dict[str, Any]] = {}
    for key in model_keys:
        model_agg[key] = {
            "total_cases": 0,
            "total_latency_ms": 0.0,
            "dimension_totals": {d: 0.0 for d in DIMENSIONS},
            "weighted_total": 0.0,
        }

    case_details = []
    for summary in summaries:
        case_entry: dict[str, Any] = {
            "id": summary.case_id,
            "description": summary.description,
            "category": summary.category,
            "models": {},
        }
        for key in model_keys:
            result = summary.results_by_model.get(key)
            if result is None:
                continue
            agg = model_agg[key]
            agg["total_cases"] += 1
            agg["total_latency_ms"] += result.latency_ms
            agg["weighted_total"] += result.judge.weighted_score
            for dim in DIMENSIONS:
                agg["dimension_totals"][dim] += result.judge.scores.get(
                    dim, DimensionScore(0, "")
                ).score

            case_entry["models"][key] = {
                "stl_text": result.stl_text,
                "latency_ms": result.latency_ms,
                "weighted_score": result.judge.weighted_score,
                "scores": {
                    dim: {
                        "score": result.judge.scores[dim].score,
                        "reason": result.judge.scores[dim].reason,
                    }
                    for dim in DIMENSIONS
                    if dim in result.judge.scores
                },
                "overall_comment": result.judge.overall_comment,
                "parse_error": result.judge.parse_error or None,
            }

        case_details.append(case_entry)

    # Build model leaderboard
    leaderboard = []
    for key in model_keys:
        agg = model_agg[key]
        n = max(agg["total_cases"], 1)
        entry = {
            "model": key,
            "cases_evaluated": agg["total_cases"],
            "avg_weighted_score": round(agg["weighted_total"] / n, 2),
            "avg_latency_ms": round(agg["total_latency_ms"] / n, 1),
            "avg_dimensions": {
                dim: round(agg["dimension_totals"][dim] / n, 2)
                for dim in DIMENSIONS
            },
        }
        leaderboard.append(entry)

    # Sort by weighted score desc
    leaderboard.sort(key=lambda x: x["avg_weighted_score"], reverse=True)

    return {
        "judge_model": judge_spec,
        "dimension_weights": DIMENSION_WEIGHTS,
        "leaderboard": leaderboard,
        "cases": case_details,
    }


def _print_summary(report: dict[str, Any]) -> None:
    """Print a human-readable summary to stdout."""
    print("\n" + "=" * 70)
    print("  STL Prompt Optimization Benchmark Report")
    print("=" * 70)
    print(f"  Judge: {report['judge_model']}")
    print(f"  Cases: {len(report['cases'])}")
    print()

    # Leaderboard
    print("  ┌─ Leaderboard ──────────────────────────────────────────┐")
    print(f"  │ {'Model':<30} {'Score':>7} {'Latency':>10} │")
    print(f"  │ {'─'*30} {'─'*7} {'─'*10} │")
    for entry in report["leaderboard"]:
        model = entry["model"]
        score = entry["avg_weighted_score"]
        latency = entry["avg_latency_ms"]
        print(f"  │ {model:<30} {score:>7.2f} {latency:>8.0f}ms │")
    print("  └───────────────────────────────────────────────────────┘")
    print()

    # Dimension breakdown per model
    print("  ┌─ Dimension Breakdown ──────────────────────────────────┐")
    dim_short = {
        "completeness": "COMPL",
        "predicate_choice": "PRED",
        "argument_correctness": "ARG",
        "correction_handling": "CORR",
        "modifier_attachment": "MOD",
        "no_hallucination": "HALL",
        "format_compliance": "FMT",
    }
    header = f"  │ {'Model':<20}"
    for dim in DIMENSIONS:
        header += f" {dim_short[dim]:>5}"
    header += " │"
    print(header)
    print(f"  │ {'─'*20}" + "".join(f" {'─'*5}" for _ in DIMENSIONS) + " │")
    for entry in report["leaderboard"]:
        row = f"  │ {entry['model']:<20}"
        for dim in DIMENSIONS:
            val = entry["avg_dimensions"][dim]
            row += f" {val:>5.1f}"
        row += " │"
        print(row)
    print("  └───────────────────────────────────────────────────────┘")
    print()

    # Per-case details (brief)
    for case in report["cases"]:
        print(f"  Case: {case['id']} ({case['category']})")
        print(f"    {case['description']}")
        for model_key, mdata in case["models"].items():
            ws = mdata["weighted_score"]
            lat = mdata["latency_ms"]
            comment = mdata.get("overall_comment", "")[:60]
            print(f"    {model_key:<30} score={ws:.2f}  {lat:.0f}ms  {comment}")
        print()


# ── CLI ──────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="STL prompt optimization benchmark runner.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--toml", type=Path, default=_DEFAULT_TEST_TOML,
        help="Config TOML file (default: mindt.toml).",
    )
    parser.add_argument(
        "--models", nargs="+", required=True,
        help="Models to benchmark as provider:model (e.g. aapi:gpt-5.4-nano leihuo:deepseek-v3.2).",
    )
    parser.add_argument(
        "--judge", type=str, default="aapi:gpt-5.4-nano",
        help="Judge model as provider:model (default: aapi:gpt-5.4-nano).",
    )
    parser.add_argument(
        "--case", type=Path, default=None,
        help="Single case JSON file or directory (default: all cases in prompt_opt/cases/).",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Output JSON report path (default: tests/eval/reports/).",
    )
    parser.add_argument(
        "--pretty", action="store_true",
        help="Pretty-print console summary.",
    )
    args = parser.parse_args(argv)

    # Load config
    cfg_mgr = ConfigManager(toml_path=args.toml)
    base_cfg = cfg_mgr.get()
    configure_runtime_logging(base_cfg.logging)

    # Parse model specs
    model_specs = [_parse_model_spec(s) for s in args.models]
    judge_provider, judge_model = _parse_model_spec(args.judge)

    # Create LLM instances
    llm_instances: dict[str, Any] = {}
    for provider, model in model_specs:
        key = f"{provider}:{model}"
        if key not in llm_instances:
            llm_instances[key] = _create_llm(cfg_mgr, provider, model)
            print(f"  [init] {key}")

    # Create judge LLM (ensure it's different from extraction when possible)
    judge_key = f"{judge_provider}:{judge_model}"
    judge_llm = _create_llm(cfg_mgr, judge_provider, judge_model)
    print(f"  [judge] {judge_key}")
    print()

    # Load cases
    cases_path = args.case.resolve() if args.case else DEFAULT_CASES_DIR
    cases = _load_cases(cases_path)
    if not cases:
        sys.exit(f"Error: no cases found at {cases_path}")
    print(f"  Loaded {len(cases)} case(s) from {cases_path}")
    print(f"  Testing {len(model_specs)} model(s): {', '.join(f'{p}:{m}' for p, m in model_specs)}")
    print()

    # Run evaluations
    summaries: list[CaseSummary] = []
    total_evals = len(cases) * len(model_specs)
    eval_count = 0

    for case in cases:
        print(f"  ── {case['id']} ──")
        summary = CaseSummary(
            case_id=case["id"],
            description=case.get("description", ""),
            category=case.get("category", ""),
        )

        conversation = _case_conversation(case)
        golden_stl = case.get("golden_stl", "")

        for provider, model in model_specs:
            key = f"{provider}:{model}"
            llm = llm_instances[key]
            eval_count += 1

            # Extract
            extraction = _extract_stl(llm, conversation)
            print(f"    {key}: extracted {len(extraction.stl_text)} chars in {extraction.latency_ms:.0f}ms")

            # Judge
            judge_result = judge_evaluate(
                judge_llm=judge_llm,
                conversation=conversation,
                golden_stl=golden_stl,
                actual_stl=extraction.stl_text,
            )
            if judge_result.parse_error:
                print(f"    ⚠ judge parse error: {judge_result.parse_error}")
            else:
                print(f"    {key}: score={judge_result.weighted_score:.2f}")

            summary.results_by_model[key] = CaseModelResult(
                case_id=case["id"],
                model=model,
                provider=provider,
                stl_text=extraction.stl_text,
                latency_ms=extraction.latency_ms,
                judge=judge_result,
            )

        summaries.append(summary)
        print()

    # Build report
    report = _build_report(summaries, model_specs, args.judge)

    # Save JSON report
    if args.output:
        output_path = args.output.resolve()
    else:
        models_tag = "_".join(m.replace(":", "-") for _, m in model_specs)
        output_path = DEFAULT_OUTPUT_DIR / f"prompt_opt_{models_tag}_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  Report saved to: {output_path}")

    # Print summary
    if args.pretty:
        _print_summary(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
