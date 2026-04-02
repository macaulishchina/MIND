"""A/B test runner for STL extraction prompt variants.

Compares STL extraction quality under two configurations:
  - Arm A: base STL extraction prompt (stl_extraction_supplement = false)
  - Arm B: base + supplement prompt (stl_extraction_supplement = true)

Each arm can use a different model — enabling comparisons like
"strong model + base prompt" vs "weak model + extended prompt".

Supports two evaluation modes:
  1. Structured expectations (tests/eval/cases/*.json with stages.stl_extract)
  2. LLM-as-judge with golden_stl (tests/eval/prompt_opt/cases/*.json)

Usage examples:

  # Same model, prompt A/B, structured eval:
  python tests/eval/runners/eval_stl_ab.py \\
      --toml mindt.toml \\
      --model gpt-5.4-nano \\
      --case tests/eval/cases/

  # Cross-model A/B with LLM-as-judge:
  python tests/eval/runners/eval_stl_ab.py \\
      --toml mindt.toml \\
      --model-a claude-opus-4-6 --model-b gpt-5.4-nano \\
      --case tests/eval/prompt_opt/cases/ \\
      --judge gpt-5.4-nano

  # Single case:
  python tests/eval/runners/eval_stl_ab.py \\
      --toml mindt.toml \\
      --model gpt-5.4-nano \\
      --case tests/eval/prompt_opt/cases/po-basic-001.json \\
      --judge gpt-5.4-nano

  # JSON output:
  python tests/eval/runners/eval_stl_ab.py \\
      --toml mindt.toml \\
      --model gpt-5.4-nano \\
      --judge gpt-5.4-nano \\
      --json --output tests/eval/reports/stl_ab.json

  # Quick validation — first 5 cases, no judge, extraction only:
  python tests/eval/runners/eval_stl_ab.py \\
      --toml mindt.toml \\
      --model gpt-5.4-nano \\
      --skip-judge --limit 5

  # Full run with case-level parallelism:
  python tests/eval/runners/eval_stl_ab.py \\
      --toml mindt.toml \\
      --model gpt-5.4-nano \\
      --judge gpt-5.4-nano \\
      --concurrency 4
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mind.config import ConfigManager
from mind.config.manager import _DEFAULT_TEST_TOML
from mind.llms.factory import LlmFactory
from mind.runtime_logging import configure_runtime_logging
from mind.stl.parser import parse_program
from mind.stl.prompt import (
    STL_EXTRACTION_SYSTEM_PROMPT,
    STL_EXTRACTION_USER_TEMPLATE,
    build_stl_extraction_prompt,
    format_focus_stack,
)
from mind.utils import parse_messages

DEFAULT_CASES_DIR = PROJECT_ROOT / "tests" / "eval" / "prompt_opt" / "cases"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "tests" / "eval" / "reports"


# ── Data classes ─────────────────────────────────────────────────────


@dataclass
class ArmResult:
    """Result of running a single case under one arm."""
    arm: str
    model: str
    supplement: bool
    case_id: str
    stl_text: str
    ref_count: int
    stmt_count: int
    note_count: int
    failed_count: int
    elapsed_s: float
    # Structured eval (when stage expectations exist)
    ref_hits: int = 0
    ref_total: int = 0
    stmt_hits: int = 0
    stmt_total: int = 0
    failures: list[str] = field(default_factory=list)
    # LLM-as-judge eval (when golden_stl + judge model provided)
    judge_score: float | None = None
    judge_details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ABCaseResult:
    """Side-by-side comparison of A and B for one case."""
    case_id: str
    description: str
    eval_mode: str  # "structured" | "judge" | "parse_only"
    arm_a: ArmResult
    arm_b: ArmResult
    winner: str  # "A", "B", "TIE"
    notes: list[str] = field(default_factory=list)


@dataclass
class ABReport:
    """Full A/B test report."""
    config_a: dict[str, Any]
    config_b: dict[str, Any]
    eval_mode: str
    cases: list[ABCaseResult]
    summary: dict[str, Any] = field(default_factory=dict)


# ── Case loading ─────────────────────────────────────────────────────


def _load_cases(source: Path) -> list[dict[str, Any]]:
    """Load cases from a file or directory.

    Supports both eval case format (stages.stl_extract) and
    prompt_opt case format (golden_stl).
    """
    resolved = source.resolve()
    if resolved.is_dir():
        case_files = sorted(resolved.glob("*.json"))
        cases = []
        for p in case_files:
            with p.open("r", encoding="utf-8") as f:
                case = json.load(f)
            # Accept cases with either stl_extract stage or golden_stl
            has_stl_stage = case.get("stages", {}).get("stl_extract")
            has_golden = case.get("golden_stl")
            has_turns = case.get("turns")
            if has_turns and (has_stl_stage or has_golden):
                cases.append(case)
        return cases
    if not resolved.exists():
        sys.exit(f"Error: case file not found: {resolved}")
    with resolved.open("r", encoding="utf-8") as f:
        return [json.load(f)]


def _case_conversation(case: dict[str, Any]) -> str:
    messages: list[dict[str, str]] = []
    for turn in case.get("turns", []):
        messages.extend(turn.get("messages", []))
    return parse_messages(messages)


def _sanitize(name: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", name.casefold()).strip("-") or "case"


# ── Structured eval helpers ──────────────────────────────────────────


def _ref_matches(row: dict[str, Any], expectation: dict[str, Any]) -> bool:
    for key in ("scope", "ref_type", "key"):
        if key in expectation and row.get(key) != expectation[key]:
            return False
    return True


def _statement_matches(row: dict[str, Any], expectation: dict[str, Any]) -> bool:
    if expectation.get("predicate") and row.get("predicate") != expectation["predicate"]:
        return False
    if "args" in expectation and row.get("args") != expectation["args"]:
        return False
    if expectation.get("args_contains"):
        flat = json.dumps(row.get("args", []), ensure_ascii=False)
        if not all(str(label) in flat for label in expectation["args_contains"]):
            return False
    return True


def _render_parsed_ref(ref) -> dict[str, Any]:
    expr = ref.expr
    return {
        "scope": getattr(expr.scope, "value", expr.scope),
        "ref_type": str(expr.ref_type).casefold() if expr.ref_type else None,
        "key": expr.key,
    }


def _render_parsed_arg(arg, refs_by_local_id) -> Any:
    kind = getattr(arg, "kind", None)
    if kind == "ref":
        if arg.ref_id in {"s", "self"}:
            return "@self"
        expr = refs_by_local_id.get(arg.ref_id)
        if expr is not None:
            ref_type = getattr(expr, "ref_type", None)
            key = getattr(expr, "key", None)
            if ref_type and key:
                return f'@{str(ref_type).casefold()}("{key}")'
        return f"@{arg.ref_id}"
    if kind == "prop":
        return f"${arg.prop_id}"
    if kind == "number":
        v = arg.value
        return int(v) if isinstance(v, float) and v.is_integer() else v
    if kind == "literal":
        return arg.value
    return str(arg)


def _render_parsed_stmt(stmt, refs_by_local_id) -> dict[str, Any]:
    return {
        "predicate": stmt.predicate,
        "args": [_render_parsed_arg(a, refs_by_local_id) for a in stmt.args],
    }


def _eval_structured(program, stage: dict[str, Any]) -> tuple[int, int, int, int, list[str]]:
    """Evaluate against structured expectations. Returns (ref_hits, ref_total, stmt_hits, stmt_total, failures)."""
    refs = [_render_parsed_ref(r) for r in program.refs]
    refs_by_local_id = {ref.local_id: ref.expr for ref in program.refs}
    stmts = [_render_parsed_stmt(s, refs_by_local_id) for s in program.statements]
    failures: list[str] = []

    ref_hits = ref_total = 0
    for exp in stage.get("expected_refs", []):
        ref_total += 1
        if any(_ref_matches(r, exp) for r in refs):
            ref_hits += 1
        else:
            failures.append(f"missing_ref:{exp}")

    stmt_hits = stmt_total = 0
    for exp in stage.get("expected_statements", []):
        stmt_total += 1
        if any(_statement_matches(s, exp) for s in stmts):
            stmt_hits += 1
        else:
            failures.append(f"missing_stmt:{exp}")

    return ref_hits, ref_total, stmt_hits, stmt_total, failures


# ── LLM-as-judge ────────────────────────────────────────────────────

# Lightweight inline judge — uses the same 7 dimensions as prompt_opt/judge.py
# but implemented inline to avoid circular imports.

JUDGE_DIMENSIONS = [
    "completeness", "predicate_choice", "argument_correctness",
    "correction_handling", "modifier_attachment",
    "no_hallucination", "format_compliance",
]
JUDGE_WEIGHTS = {
    "completeness": 0.20, "predicate_choice": 0.15,
    "argument_correctness": 0.15, "correction_handling": 0.15,
    "modifier_attachment": 0.10, "no_hallucination": 0.15,
    "format_compliance": 0.10,
}

JUDGE_SYSTEM_PROMPT = """\
You are an expert evaluator for a Semantic Translation Layer (STL) system.
Compare the ACTUAL STL output against the GOLDEN reference for quality.

Score on 7 dimensions (0–10 each):
1. completeness (20%): All facts captured?
2. predicate_choice (15%): Best predicates used?
3. argument_correctness (15%): Args correct type and order?
4. correction_handling (15%): correct_intent/retract_intent properly used? (10 if N/A)
5. modifier_attachment (10%): Modifiers on the right $id? (10 if N/A)
6. no_hallucination (15%): No invented facts?
7. format_compliance (10%): Valid STL syntax only?

Respond ONLY in JSON:
{
  "scores": {
    "completeness": {"score": <0-10>, "reason": "<brief>"},
    "predicate_choice": {"score": <0-10>, "reason": "<brief>"},
    "argument_correctness": {"score": <0-10>, "reason": "<brief>"},
    "correction_handling": {"score": <0-10>, "reason": "<brief>"},
    "modifier_attachment": {"score": <0-10>, "reason": "<brief>"},
    "no_hallucination": {"score": <0-10>, "reason": "<brief>"},
    "format_compliance": {"score": <0-10>, "reason": "<brief>"}
  }
}
"""

JUDGE_USER_TEMPLATE = """\
Conversation:
{conversation}

Golden STL:
{golden_stl}

Actual STL:
{actual_stl}

Evaluate the Actual STL quality.
"""


def _judge_eval(llm, conversation: str, golden_stl: str, actual_stl: str) -> tuple[float, dict[str, Any]]:
    """Run LLM-as-judge evaluation. Returns (weighted_score, details_dict)."""
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": JUDGE_USER_TEMPLATE.format(
            conversation=conversation,
            golden_stl=golden_stl,
            actual_stl=actual_stl,
        )},
    ]
    response = llm.generate(messages=messages, response_format={"type": "json_object"})
    # Strip markdown code fences if the model wraps JSON in ```json ... ```
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return 0.0, {"error": "judge JSON parse failed", "raw": response[:200]}

    scores = data.get("scores", {})
    weighted = 0.0
    details: dict[str, Any] = {}
    for dim in JUDGE_DIMENSIONS:
        entry = scores.get(dim, {})
        s = entry.get("score", 0) if isinstance(entry, dict) else 0
        details[dim] = s
        weighted += s * JUDGE_WEIGHTS.get(dim, 0)

    return round(weighted, 2), details


# ── Core extraction ──────────────────────────────────────────────────


def _extract_arm(
    cfg,
    case: dict[str, Any],
    arm_label: str,
    model: str | None,
    supplement: bool,
    timeout: float | None = None,
) -> ArmResult:
    """Run STL extraction for one case under one arm (no judging)."""
    case_id = case.get("id", "unknown")
    conversation = _case_conversation(case)
    stage = case.get("stages", {}).get("stl_extract", {})

    # Resolve LLM
    llm_cfg = cfg.llm_stages.get("stl_extraction", cfg.llm)
    if model or timeout is not None:
        llm_cfg = llm_cfg.model_copy(deep=True)
        if model:
            llm_cfg.model = model
        if timeout is not None:
            llm_cfg.timeout = timeout
    llm = LlmFactory.create(llm_cfg)

    # Build prompt
    system_prompt = build_stl_extraction_prompt(supplement=supplement)
    focus_stack_text = format_focus_stack([])
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": STL_EXTRACTION_USER_TEMPLATE.format(
            focus_stack=focus_stack_text,
            conversation=conversation,
        )},
    ]

    # Extract
    t0 = time.perf_counter()
    try:
        stl_text = llm.generate(messages=messages)
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        return ArmResult(
            arm=arm_label,
            model=model or llm_cfg.model,
            supplement=supplement,
            case_id=case_id,
            stl_text=f"# ERROR: {type(exc).__name__}: {exc}",
            ref_count=0, stmt_count=0, note_count=0, failed_count=0,
            elapsed_s=round(elapsed, 2),
        )
    elapsed = time.perf_counter() - t0

    # Parse
    program = parse_program(stl_text, batch_id=_sanitize(f"{arm_label}_{case_id}"))

    result = ArmResult(
        arm=arm_label,
        model=model or llm_cfg.model,
        supplement=supplement,
        case_id=case_id,
        stl_text=stl_text,
        ref_count=len(program.refs),
        stmt_count=len(program.statements),
        note_count=len(program.notes),
        failed_count=len(program.failed_lines),
        elapsed_s=round(elapsed, 2),
    )

    # Structured eval (local, no LLM call)
    if stage.get("expected_refs") or stage.get("expected_statements"):
        rh, rt, sh, st, failures = _eval_structured(program, stage)
        result.ref_hits = rh
        result.ref_total = rt
        result.stmt_hits = sh
        result.stmt_total = st
        result.failures = failures

    return result


def _judge_arm(result: ArmResult, judge_llm, conversation: str, golden_stl: str) -> None:
    """Run LLM-as-judge on a completed arm result (mutates in place)."""
    score, details = _judge_eval(judge_llm, conversation, golden_stl, result.stl_text)
    result.judge_score = score
    result.judge_details = details


def run_case_parallel(
    cfg,
    case: dict[str, Any],
    model_a: str | None,
    model_b: str | None,
    judge_llm=None,
    timeout: float | None = None,
) -> tuple[ArmResult, ArmResult]:
    """Run both arms for a case, parallelizing extraction and judging."""
    # Phase 1: parallel extraction
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_a = pool.submit(_extract_arm, cfg, case, "A", model_a, False, timeout)
        fut_b = pool.submit(_extract_arm, cfg, case, "B", model_b, True, timeout)
        arm_a = fut_a.result()
        arm_b = fut_b.result()

    # Phase 2: parallel judging
    golden_stl = case.get("golden_stl", "")
    if golden_stl and judge_llm is not None:
        conversation = _case_conversation(case)
        with ThreadPoolExecutor(max_workers=2) as pool:
            pool.submit(_judge_arm, arm_a, judge_llm, conversation, golden_stl)
            pool.submit(_judge_arm, arm_b, judge_llm, conversation, golden_stl)
            pool.shutdown(wait=True)

    return arm_a, arm_b


# ── Comparison ───────────────────────────────────────────────────────


def compare_arms(case: dict[str, Any], a: ArmResult, b: ArmResult) -> ABCaseResult:
    """Compare two arm results and determine winner."""
    notes: list[str] = []
    stage = case.get("stages", {}).get("stl_extract", {})
    golden_stl = case.get("golden_stl", "")

    # Determine eval mode and scoring
    has_structured = bool(stage.get("expected_refs") or stage.get("expected_statements"))
    has_judge = a.judge_score is not None and b.judge_score is not None

    if has_judge:
        eval_mode = "judge"
        a_score = a.judge_score or 0
        b_score = b.judge_score or 0
    elif has_structured:
        eval_mode = "structured"
        a_total = a.ref_total + a.stmt_total
        b_total = b.ref_total + b.stmt_total
        a_hits = a.ref_hits + a.stmt_hits
        b_hits = b.ref_hits + b.stmt_hits
        a_score = a_hits / a_total if a_total else 0.5
        b_score = b_hits / b_total if b_total else 0.5
    else:
        eval_mode = "parse_only"
        # Prefer more statements, fewer failures
        a_score = a.stmt_count - a.failed_count * 2
        b_score = b.stmt_count - b.failed_count * 2

    if abs(a_score - b_score) < 0.01:
        winner = "TIE"
    elif a_score > b_score:
        winner = "A"
    else:
        winner = "B"

    if a.stmt_count != b.stmt_count:
        notes.append(f"stmt_count: A={a.stmt_count} B={b.stmt_count}")
    if a.failed_count or b.failed_count:
        notes.append(f"failed: A={a.failed_count} B={b.failed_count}")

    return ABCaseResult(
        case_id=case.get("id", "unknown"),
        description=case.get("description", ""),
        eval_mode=eval_mode,
        arm_a=a,
        arm_b=b,
        winner=winner,
        notes=notes,
    )


def summarize(results: list[ABCaseResult]) -> dict[str, Any]:
    total = len(results)
    a_wins = sum(1 for r in results if r.winner == "A")
    b_wins = sum(1 for r in results if r.winner == "B")
    ties = sum(1 for r in results if r.winner == "TIE")

    a_elapsed = sum(r.arm_a.elapsed_s for r in results)
    b_elapsed = sum(r.arm_b.elapsed_s for r in results)

    s: dict[str, Any] = {
        "total_cases": total,
        "a_wins": a_wins,
        "b_wins": b_wins,
        "ties": ties,
        "a_total_elapsed_s": round(a_elapsed, 2),
        "b_total_elapsed_s": round(b_elapsed, 2),
    }

    # Judge-mode aggregate
    judge_results = [r for r in results if r.eval_mode == "judge"]
    if judge_results:
        a_scores = [r.arm_a.judge_score for r in judge_results if r.arm_a.judge_score is not None]
        b_scores = [r.arm_b.judge_score for r in judge_results if r.arm_b.judge_score is not None]
        s["a_avg_judge_score"] = round(sum(a_scores) / len(a_scores), 2) if a_scores else None
        s["b_avg_judge_score"] = round(sum(b_scores) / len(b_scores), 2) if b_scores else None

    # Structured-mode aggregate
    struct_results = [r for r in results if r.eval_mode == "structured"]
    if struct_results:
        a_hits = sum(r.arm_a.ref_hits + r.arm_a.stmt_hits for r in struct_results)
        a_total = sum(r.arm_a.ref_total + r.arm_a.stmt_total for r in struct_results)
        b_hits = sum(r.arm_b.ref_hits + r.arm_b.stmt_hits for r in struct_results)
        b_total = sum(r.arm_b.ref_total + r.arm_b.stmt_total for r in struct_results)
        s["a_structured_accuracy"] = round(a_hits / a_total, 4) if a_total else None
        s["b_structured_accuracy"] = round(b_hits / b_total, 4) if b_total else None

    return s


# ── Pretty print ─────────────────────────────────────────────────────

def _print_case_result(comparison: ABCaseResult) -> None:
    """Print a single-line result for a case."""
    tag = {"A": "A▲", "B": "B▲", "TIE": "=="}[comparison.winner]
    a = comparison.arm_a
    b = comparison.arm_b
    if comparison.eval_mode == "judge":
        print(f"[{tag}] A:{a.judge_score} B:{b.judge_score}")
    elif comparison.eval_mode == "structured":
        ah = a.ref_hits + a.stmt_hits
        at = a.ref_total + a.stmt_total
        bh = b.ref_hits + b.stmt_hits
        bt = b.ref_total + b.stmt_total
        print(f"[{tag}] A:{ah}/{at} B:{bh}/{bt}")
    else:
        print(f"[{tag}] A:{a.stmt_count}stmts B:{b.stmt_count}stmts")

def print_report(report: ABReport) -> None:
    ca = report.config_a
    cb = report.config_b
    print(f"\n{'='*70}")
    print(f"  STL Extraction A/B Test  ({report.eval_mode})")
    print(f"  Arm A: model={ca['model']}, supplement={ca['supplement']}")
    print(f"  Arm B: model={cb['model']}, supplement={cb['supplement']}")
    print(f"{'='*70}\n")

    for r in report.cases:
        tag = {"A": "← A wins", "B": "B wins →", "TIE": "  TIE   "}[r.winner]
        a = r.arm_a
        b = r.arm_b
        print(f"  [{tag}] {r.case_id}")

        if r.eval_mode == "judge":
            print(f"    A: score={a.judge_score}  stmts={a.stmt_count}  {a.elapsed_s}s")
            print(f"    B: score={b.judge_score}  stmts={b.stmt_count}  {b.elapsed_s}s")
        elif r.eval_mode == "structured":
            print(f"    A: refs={a.ref_hits}/{a.ref_total}  stmts={a.stmt_hits}/{a.stmt_total}  {a.elapsed_s}s")
            print(f"    B: refs={b.ref_hits}/{b.ref_total}  stmts={b.stmt_hits}/{b.stmt_total}  {b.elapsed_s}s")
        else:
            print(f"    A: stmts={a.stmt_count}  failed={a.failed_count}  {a.elapsed_s}s")
            print(f"    B: stmts={b.stmt_count}  failed={b.failed_count}  {b.elapsed_s}s")

        if r.notes:
            for note in r.notes:
                print(f"    * {note}")
        print()

    s = report.summary
    print(f"{'─'*70}")
    print(f"  Summary: A wins {s['a_wins']} | B wins {s['b_wins']} | "
          f"TIE {s['ties']} / {s['total_cases']} cases")
    if s.get("a_avg_judge_score") is not None:
        print(f"  Judge score: A={s['a_avg_judge_score']}  B={s['b_avg_judge_score']}")
    if s.get("a_structured_accuracy") is not None:
        print(f"  Structured: A={s['a_structured_accuracy']:.1%}  "
              f"B={s['b_structured_accuracy']:.1%}")
    print(f"  Total time: A={s['a_total_elapsed_s']}s  B={s['b_total_elapsed_s']}s")
    if s.get("wall_clock_s") is not None:
        print(f"  Wall clock: {s['wall_clock_s']}s")
    print(f"{'─'*70}\n")


# ── Entry point ──────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="A/B test for STL extraction prompt variants",
    )
    parser.add_argument(
        "--toml", type=Path, default=_DEFAULT_TEST_TOML,
        help="TOML config file (default: mindt.toml)",
    )
    parser.add_argument(
        "--case", type=Path, default=None,
        help="Case file or directory (default: tests/eval/prompt_opt/cases/)",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Model for both arms (shortcut for --model-a + --model-b)",
    )
    parser.add_argument(
        "--model-a", type=str, default=None,
        help="Model for arm A (base prompt)",
    )
    parser.add_argument(
        "--model-b", type=str, default=None,
        help="Model for arm B (supplemented prompt)",
    )
    parser.add_argument(
        "--judge", type=str, default=None,
        help="Judge model for LLM-as-judge eval (requires golden_stl in cases)",
    )
    parser.add_argument(
        "--skip-judge", action="store_true",
        help="Skip LLM-as-judge evaluation (extraction + parse only)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only run the first N cases (for quick validation)",
    )
    parser.add_argument(
        "--timeout", type=float, default=None,
        help="Per-request LLM timeout in seconds (overrides config)",
    )
    parser.add_argument(
        "--concurrency", type=int, default=1,
        help="Number of cases to run in parallel (default: 1)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output JSON report instead of pretty-print",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Write JSON report to this file",
    )
    args = parser.parse_args()

    model_a = args.model_a or args.model
    model_b = args.model_b or args.model

    mgr = ConfigManager(args.toml)
    cfg = mgr.get()
    configure_runtime_logging(cfg.logging)

    case_path = args.case.resolve() if args.case else DEFAULT_CASES_DIR
    cases = _load_cases(case_path)
    if not cases:
        sys.exit("No usable cases found (need turns + stl_extract stage or golden_stl)")

    if args.limit and args.limit < len(cases):
        cases = cases[:args.limit]

    # Judge LLM
    judge_llm = None
    if args.judge and not args.skip_judge:
        judge_cfg = cfg.llm.model_copy(deep=True)
        judge_cfg.model = args.judge
        judge_llm = LlmFactory.create(judge_cfg)

    resolved_model = model_a or cfg.llm_stages.get("stl_extraction", cfg.llm).model
    concurrency = max(1, args.concurrency)
    print(f"Running STL A/B test: {len(cases)} cases, concurrency={concurrency}")
    print(f"  Arm A: model={model_a or resolved_model}, supplement=False")
    print(f"  Arm B: model={model_b or resolved_model}, supplement=True")
    if judge_llm:
        print(f"  Judge: {args.judge}")
    elif args.skip_judge:
        print(f"  Judge: SKIPPED")
    print()

    wall_t0 = time.perf_counter()
    results: list[ABCaseResult] = []

    def _run_one(i: int, case: dict[str, Any]) -> ABCaseResult:
        cid = case.get("id", f"case-{i}")
        arm_a, arm_b = run_case_parallel(cfg, case, model_a, model_b, judge_llm, timeout=args.timeout)
        return compare_arms(case, arm_a, arm_b)

    if concurrency <= 1:
        # Sequential — with live progress
        for i, case in enumerate(cases, 1):
            cid = case.get("id", f"case-{i}")
            print(f"  [{i}/{len(cases)}] {cid} ...", end=" ", flush=True)
            comparison = _run_one(i, case)
            results.append(comparison)
            _print_case_result(comparison)
    else:
        # Concurrent cases
        futures = {}
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for i, case in enumerate(cases, 1):
                fut = pool.submit(_run_one, i, case)
                futures[fut] = (i, case)
            for fut in as_completed(futures):
                i, case = futures[fut]
                cid = case.get("id", f"case-{i}")
                comparison = fut.result()
                results.append(comparison)
                print(f"  [{i}/{len(cases)}] {cid} ... ", end="")
                _print_case_result(comparison)
        # Sort by original order
        case_order = {case.get("id", f"case-{i}"): i for i, case in enumerate(cases, 1)}
        results.sort(key=lambda r: case_order.get(r.case_id, 0))

    wall_elapsed = time.perf_counter() - wall_t0

    # Determine dominant eval mode
    eval_modes = set(r.eval_mode for r in results)
    dominant = "judge" if "judge" in eval_modes else ("structured" if "structured" in eval_modes else "parse_only")

    summary = summarize(results)
    summary["wall_clock_s"] = round(wall_elapsed, 2)

    report = ABReport(
        config_a={"model": model_a or resolved_model, "supplement": False},
        config_b={"model": model_b or resolved_model, "supplement": True},
        eval_mode=dominant,
        cases=results,
        summary=summary,
    )

    if args.json or args.output:
        data = asdict(report)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"\nReport written to {args.output}")
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print_report(report)


if __name__ == "__main__":
    main()
