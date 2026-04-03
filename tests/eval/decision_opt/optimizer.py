"""Offline optimizer for UPDATE_DECISION_SYSTEM_PROMPT."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from tests.eval.decision_opt.ab import evaluate_ab, evaluate_single_prompt
from tests.eval.decision_opt.core import (
    DEFAULT_OUTPUT_DIR,
    DecisionABCaseResult,
    DecisionArmResult,
    DecisionCase,
    build_report,
    current_runtime_prompt,
    prompt_metadata,
    summarize_arm,
)

FOCUS_CATEGORIES = (
    "action_selection",
    "id_grounding",
    "text_discipline",
    "prompt_structure",
)

OPTIMIZER_SYSTEM_PROMPT = """\
You improve a system prompt for a memory decision task.

Return JSON only:
{
  "change_category": "action_selection" | "id_grounding" | "text_discipline" | "prompt_structure",
  "candidate_prompt": "<full revised system prompt>",
  "rationale": "<brief explanation>"
}

Rules:
- Change only ONE category in this round.
- Keep the output schema identical: action, id, text, reason.
- Use calm declarative language.
- Avoid negative examples and avoid very long prompts.
- Keep the candidate focused on canonical memory strings, temporary ids, and JSON output.
"""

OPTIMIZER_USER_TEMPLATE = """\
Current system prompt:

{current_prompt}

Focus category for this round: {focus_category}

Metric summary:
{metric_summary}

Top failure cases:
{failure_digest}

Produce one candidate full system prompt that improves the selected focus category.
"""


@dataclass
class CandidateProposal:
    prompt_text: str
    change_category: str
    rationale: str
    source: str
    raw_response: str = ""
    parse_error: str = ""


@dataclass
class GateDecision:
    promote: bool
    reasons: list[str]
    protected_regressions: list[str]
    metrics: dict[str, Any]


def default_artifacts_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return DEFAULT_OUTPUT_DIR / "decision_opt" / stamp


def select_focus_category(summary: dict[str, Any]) -> str:
    ranked = [
        ("action_selection", summary.get("acceptable_action_accuracy", 0.0)),
        ("id_grounding", summary.get("id_accuracy", 0.0)),
        ("text_discipline", summary.get("text_constraint_pass_rate", 0.0)),
        ("prompt_structure", summary.get("parse_success_rate", 0.0)),
    ]
    ranked.sort(key=lambda item: item[1])
    return ranked[0][0]


def failure_digest(results: list[DecisionArmResult], limit: int = 5) -> list[dict[str, Any]]:
    failed = [result for result in results if not result.score.case_pass]
    failed.sort(key=lambda item: (item.score.composite_score, item.case_id))
    digest: list[dict[str, Any]] = []
    for result in failed[:limit]:
        digest.append(
            {
                "case_id": result.case_id,
                "cluster": result.cluster,
                "action": result.parsed.action,
                "id": result.parsed.id,
                "text": result.parsed.text,
                "reason": result.parsed.reason,
                "parse_error": result.parsed.parse_error,
                "deterministic_score": asdict(result.score),
            }
        )
    return digest


def heuristic_candidate_prompt(
    focus_category: str,
    round_index: int = 1,
) -> CandidateProposal:
    focus_line = {
        "action_selection": (
            "- Focus this round: tighten the boundary between NONE, UPDATE, and ADD by "
            "comparing subject and field before wording."
        ),
        "id_grounding": (
            "- Focus this round: be strict about choosing the single best temporary id "
            "and never reference a different subject's id."
        ),
        "text_discipline": (
            "- Focus this round: keep ADD/UPDATE text to one canonical memory string "
            "in the existing '[subject] field=value' format."
        ),
        "prompt_structure": (
            "- Focus this round: keep the response machine-safe, short, and easy to parse."
        ),
    }[focus_category]

    prompt_text = f"""\
You decide how one NEW canonical memory fact relates to a short list of EXISTING canonical memories.

Inputs:
1. EXISTING memories, each shown as [temporary_id] canonical_text
2. NEW fact, already rendered as one canonical_text string

Choose exactly one action:
- ADD: The new fact is a distinct memory that should be stored separately.
- UPDATE: One existing memory is the same memory slot, and the new fact is the better replacement.
- DELETE: One existing memory should be removed with no replacement text kept.
- NONE: The new fact is already covered, already implied by a stricter existing memory, or not worth storing.

Decision rules:
- Compare subject and field first. The best match usually shares the same [subject] prefix and the same field key before '='.
- Choose NONE when an existing memory already says the same thing or a more complete version of the same thing.
- Choose UPDATE when exactly one existing memory clearly represents the same subject and field, and the new fact is newer, more specific, corrected, or otherwise the better replacement.
- Choose ADD when the new fact is about a different subject, a different field, or a separate fact that should coexist.
- Choose DELETE only for a clear contradiction where no replacement text should remain. If the new fact provides the replacement value, prefer UPDATE instead of DELETE.
- If multiple memories look similar, choose the single best temporary id. Do not reference an id from a different subject just because the value wording is similar.

ID rules:
- Use only the provided temporary ids exactly as shown.
- For ADD and NONE, set "id" to null.
- For UPDATE and DELETE, set "id" to one provided temporary id.

Text rules:
- For ADD, "text" must be the one canonical memory string to store.
- For UPDATE, "text" must be the one canonical memory string that should replace the target memory.
- Preserve canonical format: "[subject] field=value".
- Preserve the correct subject prefix from the new fact unless one listed memory proves that the replacement must stay on another subject.
- Do not output multiple memories, bullet lists, markdown, or explanation text inside "text".
- For DELETE and NONE, set "text" to "".

Tie-breakers:
- Same subject + same field beats same subject only.
- Same subject only beats similar wording with a different subject.
- Exact duplicate or strictly subsumed fact -> NONE.
- One clear replacement memory slot -> UPDATE.
- Uncertain and distinct -> ADD.
{focus_line}

Respond with JSON only:
{{
  "action": "ADD" | "UPDATE" | "DELETE" | "NONE",
  "id": null | "temporary_id",
  "text": "canonical memory text for ADD/UPDATE, otherwise empty string",
  "reason": "brief explanation"
}}

Canonical example:
Existing memories:
[0] [self] attribute:favorite_season=spring

New fact: [self] attribute:favorite_season=late spring

Response:
{{"action":"UPDATE","id":"0","text":"[self] attribute:favorite_season=late spring","reason":"same subject and field, newer replacement"}}
"""
    return CandidateProposal(
        prompt_text=prompt_text,
        change_category=focus_category,
        rationale=f"heuristic round {round_index} candidate emphasizing {focus_category}",
        source="heuristic",
    )


def llm_candidate_prompt(
    optimizer_llm,
    current_prompt: str,
    focus_category: str,
    metric_summary: dict[str, Any],
    failure_cases: list[dict[str, Any]],
) -> CandidateProposal:
    messages = [
        {"role": "system", "content": OPTIMIZER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": OPTIMIZER_USER_TEMPLATE.format(
                current_prompt=current_prompt,
                focus_category=focus_category,
                metric_summary=json.dumps(metric_summary, ensure_ascii=False, indent=2),
                failure_digest=json.dumps(failure_cases, ensure_ascii=False, indent=2),
            ),
        },
    ]
    raw = optimizer_llm.generate(messages=messages, response_format={"type": "json_object"})
    return _parse_candidate_response(raw)


def _parse_candidate_response(raw: str) -> CandidateProposal:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return CandidateProposal(
            prompt_text="",
            change_category="prompt_structure",
            rationale="optimizer parse failed",
            source="llm",
            raw_response=raw,
            parse_error=f"JSON parse error: {exc}",
        )
    category = str(data.get("change_category", "prompt_structure")).strip()
    if category not in FOCUS_CATEGORIES:
        category = "prompt_structure"
    prompt_text = str(data.get("candidate_prompt", "")).strip()
    rationale = str(data.get("rationale", "")).strip()
    return CandidateProposal(
        prompt_text=prompt_text,
        change_category=category,
        rationale=rationale,
        source="llm",
        raw_response=raw,
        parse_error="" if prompt_text else "optimizer returned empty candidate_prompt",
    )


def propose_candidate_prompt(
    current_prompt: str,
    focus_category: str,
    metric_summary: dict[str, Any],
    failure_cases: list[dict[str, Any]],
    round_index: int,
    optimizer_llm=None,
) -> CandidateProposal:
    if optimizer_llm is not None:
        proposal = llm_candidate_prompt(
            optimizer_llm=optimizer_llm,
            current_prompt=current_prompt,
            focus_category=focus_category,
            metric_summary=metric_summary,
            failure_cases=failure_cases,
        )
        if proposal.prompt_text and not proposal.parse_error:
            return proposal
    return heuristic_candidate_prompt(focus_category=focus_category, round_index=round_index)


def evaluate_baseline(
    cases: list[DecisionCase],
    prompt_text: str,
    llm_factory,
    prompt_label: str,
    judge_factory=None,
    concurrency: int = 4,
) -> dict[str, Any]:
    results = evaluate_single_prompt(
        cases=cases,
        prompt_text=prompt_text,
        llm_factory=llm_factory,
        prompt_label=prompt_label,
        judge_factory=judge_factory,
        concurrency=concurrency,
    )
    return {
        "prompt": prompt_metadata(prompt_label, prompt_text, getattr(llm_factory(), "model", "?")),
        "results": [asdict(result) for result in results],
        "summary": summarize_arm(results),
    }


def gate_candidate(report: dict[str, Any]) -> GateDecision:
    control = report["summary"]["arm_a"]
    candidate = report["summary"]["arm_b"]
    protected_regressions = [
        case["case_id"]
        for case in report["cases"]
        if case["protected"]
        and case["arm_a"]["score"]["case_pass"]
        and not case["arm_b"]["score"]["case_pass"]
    ]
    reasons: list[str] = []
    checks = {
        "parse_success_non_regression": candidate["parse_success_rate"] >= control["parse_success_rate"],
        "acceptable_action_non_regression": (
            candidate["acceptable_action_accuracy"] >= control["acceptable_action_accuracy"]
        ),
        "id_accuracy_non_regression": candidate["id_accuracy"] >= control["id_accuracy"],
        "composite_improves": candidate["composite_score"] > control["composite_score"],
        "protected_cases_hold": not protected_regressions,
    }
    for name, passed in checks.items():
        if not passed:
            reasons.append(name)
    return GateDecision(
        promote=all(checks.values()),
        reasons=reasons,
        protected_regressions=protected_regressions,
        metrics={
            "control": control,
            "candidate": candidate,
            "checks": checks,
        },
    )


def replace_runtime_prompt_source(source_text: str, new_prompt: str) -> str:
    pattern = re.compile(
        r'UPDATE_DECISION_SYSTEM_PROMPT = """\\\n.*?\n"""',
        re.DOTALL,
    )
    replacement = (
        'UPDATE_DECISION_SYSTEM_PROMPT = """\\\n'
        + new_prompt.rstrip("\n")
        + '\n"""'
    )
    updated, count = pattern.subn(replacement, source_text, count=1)
    if count != 1:
        raise ValueError("Failed to locate UPDATE_DECISION_SYSTEM_PROMPT in source")
    return updated


def promote_runtime_prompt(prompt_path: Path, new_prompt: str) -> None:
    source_text = prompt_path.read_text(encoding="utf-8")
    updated = replace_runtime_prompt_source(source_text, new_prompt)
    prompt_path.write_text(updated, encoding="utf-8")


def run_optimization_rounds(
    *,
    cases: list[DecisionCase],
    control_prompt: str,
    llm_factory,
    prompt_label: str,
    rounds: int,
    artifacts_dir: Path,
    concurrency: int = 4,
    judge_factory=None,
    optimizer_llm_factory=None,
) -> dict[str, Any]:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    baseline_results = evaluate_single_prompt(
        cases=cases,
        prompt_text=control_prompt,
        llm_factory=llm_factory,
        prompt_label=prompt_label,
        judge_factory=judge_factory,
        concurrency=concurrency,
    )
    baseline_payload = {
        "prompt": prompt_metadata(prompt_label, control_prompt, getattr(llm_factory(), "model", "?")),
        "results": [asdict(result) for result in baseline_results],
        "summary": summarize_arm(baseline_results),
    }
    (artifacts_dir / "baseline_report.json").write_text(
        json.dumps(baseline_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    current_prompt = control_prompt
    current_summary = baseline_payload["summary"]
    current_results = baseline_results
    rounds_payload: list[dict[str, Any]] = []

    for round_index in range(1, rounds + 1):
        focus_category = select_focus_category(current_summary)
        candidate = propose_candidate_prompt(
            current_prompt=current_prompt,
            focus_category=focus_category,
            metric_summary=current_summary,
            failure_cases=failure_digest(current_results),
            round_index=round_index,
            optimizer_llm=optimizer_llm_factory() if optimizer_llm_factory is not None else None,
        )
        candidate_path = artifacts_dir / f"round_{round_index:02d}_candidate_prompt.txt"
        candidate_path.write_text(candidate.prompt_text, encoding="utf-8")

        case_results = evaluate_ab(
            cases=cases,
            prompt_a=current_prompt,
            prompt_b=candidate.prompt_text,
            llm_factory_a=llm_factory,
            llm_factory_b=llm_factory,
            prompt_label_a=f"control-r{round_index:02d}",
            prompt_label_b=f"candidate-r{round_index:02d}",
            judge_factory=judge_factory,
            concurrency=concurrency,
        )
        report = build_report(
            case_results=case_results,
            prompt_a=prompt_metadata(
                f"control-r{round_index:02d}",
                current_prompt,
                getattr(llm_factory(), "model", "?"),
            ),
            prompt_b=prompt_metadata(
                f"candidate-r{round_index:02d}",
                candidate.prompt_text,
                getattr(llm_factory(), "model", "?"),
            ),
            judge_model=getattr(judge_factory(), "model", None) if judge_factory is not None else None,
        )
        gate = gate_candidate(report)

        (artifacts_dir / f"round_{round_index:02d}_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (artifacts_dir / f"round_{round_index:02d}_gate.json").write_text(
            json.dumps(asdict(gate), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        rounds_payload.append(
            {
                "round": round_index,
                "focus_category": focus_category,
                "candidate": asdict(candidate),
                "gate": asdict(gate),
                "summary": report["summary"],
            }
        )

        if gate.promote:
            current_prompt = candidate.prompt_text
            current_results = [case.arm_b for case in case_results]
            current_summary = report["summary"]["arm_b"]

    summary_payload = {
        "baseline_summary": baseline_payload["summary"],
        "final_summary": current_summary,
        "final_prompt": current_prompt,
        "rounds": rounds_payload,
    }
    (artifacts_dir / "campaign_summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary_payload


__all__ = [
    "CandidateProposal",
    "GateDecision",
    "default_artifacts_dir",
    "evaluate_baseline",
    "failure_digest",
    "gate_candidate",
    "heuristic_candidate_prompt",
    "promote_runtime_prompt",
    "propose_candidate_prompt",
    "replace_runtime_prompt_source",
    "run_optimization_rounds",
    "select_focus_category",
]

