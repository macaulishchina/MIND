"""Optional LLM-as-judge overlay for decision prompt evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from tests.eval.decision_opt.core import DecisionCase, DecisionArmResult

DIMENSIONS = [
    "action_reasonableness",
    "id_grounding",
    "updated_text_quality",
    "low_value_fact_suppression",
    "format_compliance",
]

DIMENSION_WEIGHTS = {
    "action_reasonableness": 0.30,
    "id_grounding": 0.20,
    "updated_text_quality": 0.20,
    "low_value_fact_suppression": 0.15,
    "format_compliance": 0.15,
}

JUDGE_SYSTEM_PROMPT = """\
You are an expert evaluator for a memory decision prompt.
Score a model's JSON decision for a new fact versus existing canonical memories.

Score each dimension from 0 to 10:
1. action_reasonableness (30%): Is the chosen ADD / UPDATE / DELETE / NONE action sensible?
2. id_grounding (20%): If UPDATE or DELETE is chosen, is the referenced temporary id the right one?
3. updated_text_quality (20%): For ADD or UPDATE, is the text a valid, minimal canonical memory string?
4. low_value_fact_suppression (15%): Does the model avoid storing trivial or low-value facts when the case expects that?
5. format_compliance (15%): Is the output valid JSON with action, id, text, and reason fields?

Respond with JSON only:
{
  "scores": {
    "action_reasonableness": {"score": <0-10>, "reason": "<brief>"},
    "id_grounding": {"score": <0-10>, "reason": "<brief>"},
    "updated_text_quality": {"score": <0-10>, "reason": "<brief>"},
    "low_value_fact_suppression": {"score": <0-10>, "reason": "<brief>"},
    "format_compliance": {"score": <0-10>, "reason": "<brief>"}
  },
  "overall_comment": "<one sentence>"
}
"""

JUDGE_USER_TEMPLATE = """\
Case:
- id: {case_id}
- description: {description}
- cluster: {cluster}
- acceptable_actions: {acceptable_actions}
- expected_action: {expected_action}
- expected_ids: {expected_ids}
- text_must_contain: {text_must_contain}
- text_must_not_contain: {text_must_not_contain}

Existing memories:
{existing_memories}

New fact:
{new_fact}

Model response:
{raw_response}

Evaluate whether the model made a good decision for this case.
"""


@dataclass
class JudgeResult:
    weighted_score: float = 0.0
    scores: dict[str, dict[str, Any]] = field(default_factory=dict)
    overall_comment: str = ""
    raw_response: str = ""
    parse_error: str = ""


def evaluate(judge_llm, case: DecisionCase, arm_result: DecisionArmResult) -> JudgeResult:
    existing_memories = "\n".join(
        f"[{memory.temp_id}] {memory.content}"
        for memory in case.existing_memories
    ) or "(no existing memories)"
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": JUDGE_USER_TEMPLATE.format(
                case_id=case.id,
                description=case.description,
                cluster=case.cluster,
                acceptable_actions=", ".join(case.acceptable_actions),
                expected_action=case.expected_action or "(none)",
                expected_ids=", ".join(case.expected_ids()) or "(none)",
                text_must_contain=", ".join(case.text_must_contain) or "(none)",
                text_must_not_contain=", ".join(case.text_must_not_contain) or "(none)",
                existing_memories=existing_memories,
                new_fact=case.new_fact,
                raw_response=arm_result.parsed.raw_response,
            ),
        },
    ]
    raw = judge_llm.generate(messages=messages, response_format={"type": "json_object"})
    return _parse_response(raw)


def _parse_response(raw: str) -> JudgeResult:
    result = JudgeResult(raw_response=raw)
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        result.parse_error = f"JSON parse error: {exc}"
        return result

    total = 0.0
    scores = data.get("scores", {})
    for dimension in DIMENSIONS:
        entry = scores.get(dimension, {}) if isinstance(scores, dict) else {}
        score = _clamp(entry.get("score", 0))
        reason = str(entry.get("reason", ""))
        result.scores[dimension] = {"score": score, "reason": reason}
        total += score * DIMENSION_WEIGHTS[dimension]

    result.weighted_score = round(total, 4)
    result.overall_comment = str(data.get("overall_comment", ""))
    return result


def _clamp(value: Any, lo: int = 0, hi: int = 10) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return 0

