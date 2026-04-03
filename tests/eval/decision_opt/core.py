"""Shared utilities for UPDATE_DECISION prompt evaluation."""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mind.config import ConfigManager
from mind.config.manager import _DEFAULT_TEST_TOML
from mind.llms.factory import LlmFactory
from mind.prompts import (
    UPDATE_DECISION_SYSTEM_PROMPT,
    UPDATE_DECISION_USER_TEMPLATE,
    format_existing_memories,
)
from mind.runtime_logging import configure_runtime_logging

DEFAULT_CASES_DIR = PROJECT_ROOT / "tests" / "eval" / "decision_opt" / "cases"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "tests" / "eval" / "reports"
VALID_ACTIONS = {"ADD", "UPDATE", "DELETE", "NONE"}
DEFAULT_SCORE_WEIGHTS = {
    "acceptable_action": 0.30,
    "exact_action": 0.15,
    "id_accuracy": 0.20,
    "text_constraint": 0.15,
    "parse_success": 0.10,
    "judge_quality": 0.10,
}


@dataclass
class ExistingMemory:
    temp_id: str
    content: str


@dataclass
class DecisionCase:
    id: str
    description: str
    new_fact: str
    existing_memories: list[ExistingMemory]
    acceptable_actions: list[str]
    expected_action: str | None = None
    acceptable_ids: list[str] = field(default_factory=list)
    expected_id: str | None = None
    text_must_contain: list[str] = field(default_factory=list)
    text_must_not_contain: list[str] = field(default_factory=list)
    text_must_be_empty: bool | None = None
    reason_must_contain: list[str] = field(default_factory=list)
    difficulty: str = "medium"
    cluster: str = "misc"
    protected: bool = False
    notes: str = ""

    def require_empty_text(self) -> bool:
        if self.text_must_be_empty is not None:
            return self.text_must_be_empty
        return bool(self.acceptable_actions) and all(
            action in {"DELETE", "NONE"} for action in self.acceptable_actions
        )

    def expected_ids(self) -> list[str]:
        ids = list(self.acceptable_ids)
        if self.expected_id is not None and self.expected_id not in ids:
            ids.append(self.expected_id)
        return ids


@dataclass
class ParsedDecision:
    action: str = ""
    id: str | None = None
    text: str = ""
    reason: str = ""
    raw_response: str = ""
    parse_success: bool = False
    parse_error: str = ""


@dataclass
class DecisionScore:
    parse_success: bool
    exact_action_pass: bool
    acceptable_action_pass: bool
    id_pass: bool
    text_constraint_pass: bool
    reason_constraint_pass: bool
    case_pass: bool
    judge_weighted_score: float | None = None
    composite_score: float = 0.0


@dataclass
class DecisionArmResult:
    arm: str
    prompt_label: str
    case_id: str
    description: str
    cluster: str
    protected: bool
    model: str
    provider: str
    elapsed_s: float
    parsed: ParsedDecision
    score: DecisionScore
    judge_details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionABCaseResult:
    case_id: str
    description: str
    cluster: str
    protected: bool
    arm_a: DecisionArmResult
    arm_b: DecisionArmResult
    winner: str
    notes: list[str] = field(default_factory=list)


def _safe_ratio(numerator: int, denominator: int, empty_value: float = 1.0) -> float:
    if denominator == 0:
        return empty_value
    return numerator / denominator


def _parse_model_spec(spec: str | None) -> tuple[str | None, str | None]:
    if not spec:
        return None, None
    if ":" in spec:
        provider, model = spec.split(":", 1)
        return provider.strip(), model.strip()
    return None, spec.strip()


def _configure_runner_logging(cfg) -> None:
    configure_runtime_logging(cfg.logging)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        raise ValueError(f"Expected string list, got {type(value).__name__}")
    return [str(item) for item in value]


def _normalize_action(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    if normalized not in VALID_ACTIONS:
        raise ValueError(f"Unsupported action '{value}'")
    return normalized


def _normalize_existing_memories(case_id: str, payload: dict[str, Any]) -> list[ExistingMemory]:
    memories = payload.get("existing_memories", [])
    if not isinstance(memories, list):
        raise ValueError(f"Case {case_id}: existing_memories must be a list")
    normalized: list[ExistingMemory] = []
    for idx, item in enumerate(memories):
        if not isinstance(item, dict):
            raise ValueError(f"Case {case_id}: existing memory #{idx} must be an object")
        raw_id = item.get("id")
        temp_id = str(raw_id) if raw_id is not None else str(idx)
        if temp_id != str(idx):
            raise ValueError(
                f"Case {case_id}: existing memory ids must match list order; "
                f"expected {idx}, got {temp_id}"
            )
        content = str(item.get("content", "")).strip()
        if not content:
            raise ValueError(f"Case {case_id}: existing memory #{idx} is missing content")
        normalized.append(ExistingMemory(temp_id=temp_id, content=content))
    return normalized


def _case_from_payload(payload: dict[str, Any], path: Path) -> DecisionCase:
    case_id = str(payload.get("id", path.stem)).strip()
    if not case_id:
        raise ValueError(f"Case {path} is missing an id")

    description = str(payload.get("description", "")).strip()
    if not description:
        raise ValueError(f"Case {case_id}: description is required")

    new_fact = str(payload.get("new_fact", "")).strip()
    if not new_fact:
        raise ValueError(f"Case {case_id}: new_fact is required")

    expected_action = _normalize_action(payload.get("expected_action"))
    acceptable_actions = [
        action
        for action in (_normalize_action(item) for item in _normalize_string_list(payload.get("acceptable_actions")))
        if action is not None
    ]
    if expected_action and expected_action not in acceptable_actions:
        acceptable_actions.insert(0, expected_action)
    if not acceptable_actions:
        raise ValueError(f"Case {case_id}: at least one acceptable action is required")

    acceptable_ids = _normalize_string_list(payload.get("acceptable_ids"))
    expected_id = payload.get("expected_id")
    expected_id = None if expected_id is None else str(expected_id)
    if expected_id is not None and expected_id not in acceptable_ids:
        acceptable_ids.append(expected_id)

    case = DecisionCase(
        id=case_id,
        description=description,
        new_fact=new_fact,
        existing_memories=_normalize_existing_memories(case_id, payload),
        expected_action=expected_action,
        acceptable_actions=acceptable_actions,
        expected_id=expected_id,
        acceptable_ids=acceptable_ids,
        text_must_contain=_normalize_string_list(payload.get("text_must_contain") or payload.get("expected_text_contains")),
        text_must_not_contain=_normalize_string_list(payload.get("text_must_not_contain")),
        text_must_be_empty=payload.get("text_must_be_empty"),
        reason_must_contain=_normalize_string_list(payload.get("reason_must_contain")),
        difficulty=str(payload.get("difficulty", "medium")),
        cluster=str(payload.get("cluster", "misc")),
        protected=bool(payload.get("protected", False)),
        notes=str(payload.get("notes", "")),
    )

    if case.require_empty_text() and case.text_must_contain:
        raise ValueError(
            f"Case {case_id}: text_must_contain conflicts with text_must_be_empty"
        )
    return case


def load_cases(source: Path) -> list[DecisionCase]:
    resolved = source.resolve()
    if resolved.is_dir():
        return [
            _case_from_payload(_load_json(path), path)
            for path in sorted(resolved.glob("*.json"))
        ]
    if not resolved.exists():
        raise FileNotFoundError(f"Decision case source not found: {resolved}")
    return [_case_from_payload(_load_json(resolved), resolved)]


def build_messages(case: DecisionCase, system_prompt: str) -> list[dict[str, str]]:
    existing_memories = format_existing_memories(
        [{"content": memory.content} for memory in case.existing_memories]
    )
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": UPDATE_DECISION_USER_TEMPLATE.format(
                existing_memories=existing_memories,
                new_fact=case.new_fact,
            ),
        },
    ]


def create_eval_llm(
    cfg_mgr: ConfigManager,
    model_spec: str | None = None,
):
    provider_override, model_override = _parse_model_spec(model_spec)
    overrides: dict[str, Any] = {}
    if provider_override:
        overrides["llm"] = {"provider": provider_override}
    resolved = cfg_mgr.get(overrides=overrides or None)
    llm_cfg = resolved.llm_stages.get("decision", resolved.llm).model_copy(deep=True)
    if provider_override:
        llm_cfg.provider = provider_override
    if model_override:
        llm_cfg.model = model_override
    return LlmFactory.create(llm_cfg)


def parse_decision_response(raw: str) -> ParsedDecision:
    result = ParsedDecision(raw_response=raw or "")
    text = (raw or "").strip()
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
        result.parse_error = f"JSON parse error: {exc}"
        return result

    action = _normalize_action(data.get("action"))
    if action is None:
        result.parse_error = "Response is missing a valid action"
        return result

    raw_id = data.get("id")
    if raw_id in ("", "null", None):
        parsed_id = None
    else:
        parsed_id = str(raw_id)

    text_value = data.get("text", "")
    if text_value is None:
        text_value = ""
    reason_value = data.get("reason", "")
    if reason_value is None:
        reason_value = ""

    result.action = action
    result.id = parsed_id
    result.text = str(text_value)
    result.reason = str(reason_value)
    result.parse_success = True
    return result


def score_case(
    case: DecisionCase,
    parsed: ParsedDecision,
    judge_weighted_score: float | None = None,
) -> DecisionScore:
    if not parsed.parse_success:
        return DecisionScore(
            parse_success=False,
            exact_action_pass=False,
            acceptable_action_pass=False,
            id_pass=False,
            text_constraint_pass=False,
            reason_constraint_pass=False,
            case_pass=False,
            judge_weighted_score=judge_weighted_score,
            composite_score=0.0,
        )

    exact_action_pass = bool(case.expected_action and parsed.action == case.expected_action)
    acceptable_action_pass = parsed.action in case.acceptable_actions

    expected_ids = case.expected_ids()
    if parsed.action in {"UPDATE", "DELETE"}:
        if expected_ids:
            id_pass = parsed.id in expected_ids
        else:
            id_pass = parsed.id is not None
    else:
        id_pass = parsed.id is None

    text_constraint_pass = True
    parsed_text = (parsed.text or "").strip()
    if parsed.action in {"ADD", "UPDATE"}:
        if case.text_must_contain:
            text_constraint_pass = text_constraint_pass and all(
                needle in parsed_text for needle in case.text_must_contain
            )
        if case.text_must_not_contain:
            text_constraint_pass = text_constraint_pass and all(
                needle not in parsed_text for needle in case.text_must_not_contain
            )
    if case.require_empty_text() and parsed.action in {"DELETE", "NONE"}:
        text_constraint_pass = text_constraint_pass and not parsed_text

    reason_constraint_pass = True
    if case.reason_must_contain:
        lowered_reason = parsed.reason.casefold()
        reason_constraint_pass = all(
            token.casefold() in lowered_reason
            for token in case.reason_must_contain
        )

    judge_component = max(0.0, min(10.0, judge_weighted_score or 0.0)) / 10.0
    composite = (
        DEFAULT_SCORE_WEIGHTS["acceptable_action"] * float(acceptable_action_pass)
        + DEFAULT_SCORE_WEIGHTS["exact_action"] * float(exact_action_pass)
        + DEFAULT_SCORE_WEIGHTS["id_accuracy"] * float(id_pass)
        + DEFAULT_SCORE_WEIGHTS["text_constraint"] * float(text_constraint_pass)
        + DEFAULT_SCORE_WEIGHTS["parse_success"] * float(parsed.parse_success)
        + DEFAULT_SCORE_WEIGHTS["judge_quality"] * judge_component
    )
    case_pass = (
        parsed.parse_success
        and acceptable_action_pass
        and id_pass
        and text_constraint_pass
        and reason_constraint_pass
    )
    return DecisionScore(
        parse_success=parsed.parse_success,
        exact_action_pass=exact_action_pass,
        acceptable_action_pass=acceptable_action_pass,
        id_pass=id_pass,
        text_constraint_pass=text_constraint_pass,
        reason_constraint_pass=reason_constraint_pass,
        case_pass=case_pass,
        judge_weighted_score=judge_weighted_score,
        composite_score=round(composite, 4),
    )


def run_arm(
    case: DecisionCase,
    prompt_text: str,
    llm,
    arm_label: str,
    prompt_label: str,
) -> DecisionArmResult:
    messages = build_messages(case, prompt_text)
    t0 = time.perf_counter()
    try:
        response = llm.generate(
            messages=messages,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        parsed = ParsedDecision(
            raw_response=f"{type(exc).__name__}: {exc}",
            parse_success=False,
            parse_error=f"{type(exc).__name__}: {exc}",
        )
        score = score_case(case, parsed)
        return DecisionArmResult(
            arm=arm_label,
            prompt_label=prompt_label,
            case_id=case.id,
            description=case.description,
            cluster=case.cluster,
            protected=case.protected,
            model=getattr(llm, "model", "?"),
            provider=getattr(llm, "provider", "?"),
            elapsed_s=round(elapsed, 3),
            parsed=parsed,
            score=score,
        )

    elapsed = time.perf_counter() - t0
    parsed = parse_decision_response(response)
    score = score_case(case, parsed)
    return DecisionArmResult(
        arm=arm_label,
        prompt_label=prompt_label,
        case_id=case.id,
        description=case.description,
        cluster=case.cluster,
        protected=case.protected,
        model=getattr(llm, "model", "?"),
        provider=getattr(llm, "provider", "?"),
        elapsed_s=round(elapsed, 3),
        parsed=parsed,
        score=score,
    )


def attach_judge_score(
    result: DecisionArmResult,
    case: DecisionCase,
    judge_weighted_score: float,
    judge_details: dict[str, Any],
) -> DecisionArmResult:
    return DecisionArmResult(
        arm=result.arm,
        prompt_label=result.prompt_label,
        case_id=result.case_id,
        description=result.description,
        cluster=result.cluster,
        protected=result.protected,
        model=result.model,
        provider=result.provider,
        elapsed_s=result.elapsed_s,
        parsed=result.parsed,
        score=score_case(
            case,
            result.parsed,
            judge_weighted_score=judge_weighted_score,
        ),
        judge_details=judge_details,
    )


def compare_case(
    case: DecisionCase,
    arm_a: DecisionArmResult,
    arm_b: DecisionArmResult,
) -> DecisionABCaseResult:
    notes: list[str] = []
    if arm_a.score.case_pass != arm_b.score.case_pass:
        notes.append(f"case_pass: A={arm_a.score.case_pass} B={arm_b.score.case_pass}")
    if arm_a.parsed.action != arm_b.parsed.action:
        notes.append(f"action: A={arm_a.parsed.action or '-'} B={arm_b.parsed.action or '-'}")
    if abs(arm_a.score.composite_score - arm_b.score.composite_score) < 0.0001:
        winner = "TIE"
    elif arm_a.score.composite_score > arm_b.score.composite_score:
        winner = "A"
    else:
        winner = "B"
    return DecisionABCaseResult(
        case_id=case.id,
        description=case.description,
        cluster=case.cluster,
        protected=case.protected,
        arm_a=arm_a,
        arm_b=arm_b,
        winner=winner,
        notes=notes,
    )


def summarize_arm(results: list[DecisionArmResult]) -> dict[str, Any]:
    total = len(results)
    protected = [result for result in results if result.protected]
    judged = [result for result in results if result.score.judge_weighted_score is not None]
    cluster_rollup: dict[str, dict[str, float]] = {}

    for result in results:
        bucket = cluster_rollup.setdefault(
            result.cluster,
            {
                "cases": 0,
                "case_passes": 0,
                "acceptable_action_hits": 0,
                "composite_total": 0.0,
            },
        )
        bucket["cases"] += 1
        bucket["case_passes"] += int(result.score.case_pass)
        bucket["acceptable_action_hits"] += int(result.score.acceptable_action_pass)
        bucket["composite_total"] += result.score.composite_score

    cluster_summary = {
        cluster: {
            "cases": int(data["cases"]),
            "case_pass_rate": round(_safe_ratio(int(data["case_passes"]), int(data["cases"])), 4),
            "acceptable_action_accuracy": round(
                _safe_ratio(int(data["acceptable_action_hits"]), int(data["cases"])),
                4,
            ),
            "composite_score": round(data["composite_total"] / max(1, int(data["cases"])), 4),
        }
        for cluster, data in sorted(cluster_rollup.items())
    }

    return {
        "total_cases": total,
        "parse_success_rate": round(_safe_ratio(sum(int(r.score.parse_success) for r in results), total), 4),
        "exact_action_accuracy": round(_safe_ratio(sum(int(r.score.exact_action_pass) for r in results), total), 4),
        "acceptable_action_accuracy": round(
            _safe_ratio(sum(int(r.score.acceptable_action_pass) for r in results), total),
            4,
        ),
        "id_accuracy": round(_safe_ratio(sum(int(r.score.id_pass) for r in results), total), 4),
        "text_constraint_pass_rate": round(
            _safe_ratio(sum(int(r.score.text_constraint_pass) for r in results), total),
            4,
        ),
        "reason_constraint_pass_rate": round(
            _safe_ratio(sum(int(r.score.reason_constraint_pass) for r in results), total),
            4,
        ),
        "case_pass_rate": round(_safe_ratio(sum(int(r.score.case_pass) for r in results), total), 4),
        "protected_case_pass_rate": round(
            _safe_ratio(sum(int(r.score.case_pass) for r in protected), len(protected)),
            4,
        ),
        "judge_quality": (
            round(sum((r.score.judge_weighted_score or 0.0) for r in judged) / len(judged), 4)
            if judged
            else None
        ),
        "composite_score": round(
            sum(r.score.composite_score for r in results) / max(1, total),
            4,
        ),
        "cluster_breakdown": cluster_summary,
    }


def build_report(
    case_results: list[DecisionABCaseResult],
    prompt_a: dict[str, Any],
    prompt_b: dict[str, Any],
    judge_model: str | None = None,
) -> dict[str, Any]:
    arm_a_results = [case.arm_a for case in case_results]
    arm_b_results = [case.arm_b for case in case_results]
    summary = {
        "wins": {
            "A": sum(1 for case in case_results if case.winner == "A"),
            "B": sum(1 for case in case_results if case.winner == "B"),
            "TIE": sum(1 for case in case_results if case.winner == "TIE"),
        },
        "arm_a": summarize_arm(arm_a_results),
        "arm_b": summarize_arm(arm_b_results),
    }
    return {
        "stage": "decision_prompt_ab",
        "prompt_a": prompt_a,
        "prompt_b": prompt_b,
        "judge_model": judge_model,
        "cases": [asdict(item) for item in case_results],
        "summary": summary,
    }


def render_summary(report: dict[str, Any], output_path: Path | None = None) -> str:
    arm_a = report["summary"]["arm_a"]
    arm_b = report["summary"]["arm_b"]
    wins = report["summary"]["wins"]
    lines = [
        "Decision Prompt A/B Summary",
        "",
        f"Arm A: {report['prompt_a']['label']}",
        f"  acceptable_action_accuracy={arm_a['acceptable_action_accuracy']:.3f} "
        f"id_accuracy={arm_a['id_accuracy']:.3f} "
        f"case_pass_rate={arm_a['case_pass_rate']:.3f} "
        f"composite={arm_a['composite_score']:.3f}",
        f"Arm B: {report['prompt_b']['label']}",
        f"  acceptable_action_accuracy={arm_b['acceptable_action_accuracy']:.3f} "
        f"id_accuracy={arm_b['id_accuracy']:.3f} "
        f"case_pass_rate={arm_b['case_pass_rate']:.3f} "
        f"composite={arm_b['composite_score']:.3f}",
        "",
        f"Wins: A={wins['A']} B={wins['B']} TIE={wins['TIE']}",
    ]
    if output_path is not None:
        lines.extend(["", f"Report: {output_path.resolve()}"])
    return "\n".join(lines)


def prompt_metadata(label: str, prompt_text: str, model: str) -> dict[str, Any]:
    return {
        "label": label,
        "model": model,
        "lines": len(prompt_text.strip().splitlines()),
        "characters": len(prompt_text),
    }


def current_runtime_prompt() -> str:
    return UPDATE_DECISION_SYSTEM_PROMPT


__all__ = [
    "DEFAULT_CASES_DIR",
    "DEFAULT_OUTPUT_DIR",
    "DecisionABCaseResult",
    "DecisionArmResult",
    "DecisionCase",
    "DecisionScore",
    "ExistingMemory",
    "ParsedDecision",
    "_DEFAULT_TEST_TOML",
    "_configure_runner_logging",
    "attach_judge_score",
    "build_messages",
    "build_report",
    "compare_case",
    "create_eval_llm",
    "current_runtime_prompt",
    "load_cases",
    "parse_decision_response",
    "prompt_metadata",
    "render_summary",
    "run_arm",
    "score_case",
    "summarize_arm",
]
