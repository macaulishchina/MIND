"""LLM-as-judge for STL extraction quality evaluation.

Uses a separate "judge" LLM to score STL outputs on multiple quality
dimensions. The judge sees the original conversation, a golden reference,
and the actual extraction output, then provides scores and reasoning.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from mind.llms.base import BaseLLM

logger = logging.getLogger(__name__)

# ── Scoring dimensions ───────────────────────────────────────────────

DIMENSIONS = [
    "completeness",
    "predicate_choice",
    "argument_correctness",
    "correction_handling",
    "modifier_attachment",
    "no_hallucination",
    "format_compliance",
]

DIMENSION_WEIGHTS = {
    "completeness": 0.20,
    "predicate_choice": 0.15,
    "argument_correctness": 0.15,
    "correction_handling": 0.15,
    "modifier_attachment": 0.10,
    "no_hallucination": 0.15,
    "format_compliance": 0.10,
}

# ── Judge prompt ─────────────────────────────────────────────────────

JUDGE_SYSTEM_PROMPT = """\
You are an expert evaluator for a Semantic Translation Layer (STL) system.
Your job is to assess the quality of STL extraction output by comparing it
against an original conversation and a golden reference.

STL uses 3 forms + comments:
  @id: TYPE "key"           — entity declaration
  $id = pred(arg, ...)      — semantic statement
  note($id, "text")         — free-text annotation
  # comment                 — ignored by parser

Score the output on these 7 dimensions (0–10 each):

1. **completeness** (weight 20%)
   Are ALL facts from the conversation captured? Missing facts = lower score.
   Every distinct entity, relationship, attribute, event, and modifier
   mentioned in the conversation should appear in the output.

2. **predicate_choice** (weight 15%)
   Are the correct predicates used? e.g., "brother" not "friend" for siblings,
   "believe" not "uncertain" for subjective hedging.

3. **argument_correctness** (weight 15%)
   Are arguments attached to the right predicates and in the right order?
   Are @ref and $ref links correct?

4. **correction_handling** (weight 15%)
   When corrections occur:
   - Is correct_intent used properly (only for "A→B" corrections)?
   - Is retract_intent used properly (only for "A is wrong" with no replacement)?
   - Are they mutually exclusive (never both for the same fact)?
   - Are "ghost statements" (re-stating the old wrong fact) absent?
   Score 10 if no corrections in the conversation.

5. **modifier_attachment** (weight 10%)
   Are time/degree/quantity/frequency/duration modifiers attached to the
   correct statement? e.g., "last year" should attach to "meet" not "marry"
   if that's what the conversation says.
   Score 10 if no modifiers in the conversation.

6. **no_hallucination** (weight 15%)
   Does the output contain any facts NOT stated in the conversation?
   Invented relationships, attributes, or events = lower score.

7. **format_compliance** (weight 10%)
   Is the output valid STL syntax? No markdown, no tables, no code fences,
   no explanations outside the 3 forms + comments.

Respond in this exact JSON format (no other text):
{
  "scores": {
    "completeness": {"score": <0-10>, "reason": "<brief explanation>"},
    "predicate_choice": {"score": <0-10>, "reason": "<brief explanation>"},
    "argument_correctness": {"score": <0-10>, "reason": "<brief explanation>"},
    "correction_handling": {"score": <0-10>, "reason": "<brief explanation>"},
    "modifier_attachment": {"score": <0-10>, "reason": "<brief explanation>"},
    "no_hallucination": {"score": <0-10>, "reason": "<brief explanation>"},
    "format_compliance": {"score": <0-10>, "reason": "<brief explanation>"}
  },
  "overall_comment": "<one-sentence overall assessment>"
}
"""

JUDGE_USER_TEMPLATE = """\
## Original Conversation

{conversation}

## Golden Reference STL

{golden_stl}

## Actual STL Output (to evaluate)

{actual_stl}

Evaluate the Actual STL Output against the conversation and golden reference.
"""


# ── Data structures ──────────────────────────────────────────────────

@dataclass
class DimensionScore:
    score: int
    reason: str


@dataclass
class JudgeResult:
    scores: dict[str, DimensionScore] = field(default_factory=dict)
    overall_comment: str = ""
    weighted_score: float = 0.0
    raw_response: str = ""
    parse_error: str = ""


# ── Judge logic ──────────────────────────────────────────────────────

def evaluate(
    judge_llm: BaseLLM,
    conversation: str,
    golden_stl: str,
    actual_stl: str,
) -> JudgeResult:
    """Ask the judge LLM to score a single STL extraction."""
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": JUDGE_USER_TEMPLATE.format(
                conversation=conversation,
                golden_stl=golden_stl,
                actual_stl=actual_stl,
            ),
        },
    ]

    raw = judge_llm.generate(messages=messages, temperature=0.0)
    return _parse_judge_response(raw)


def _parse_judge_response(raw: str) -> JudgeResult:
    """Parse the judge's JSON response into a JudgeResult."""
    result = JudgeResult(raw_response=raw)
    # Strip potential markdown code fences
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # drop opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    # Try to extract JSON object even if surrounded by extra text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Attempt repair: strip trailing commas before } or ]
        import re as _re
        repaired = _re.sub(r",\s*([}\]])", r"\1", text)
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError as exc:
            result.parse_error = f"JSON parse error: {exc}"
            for dim in DIMENSIONS:
                result.scores[dim] = DimensionScore(score=0, reason="judge response parse error")
            return result

    scores_data = data.get("scores", {})
    for dim in DIMENSIONS:
        entry = scores_data.get(dim, {})
        result.scores[dim] = DimensionScore(
            score=_clamp(entry.get("score", 0)),
            reason=entry.get("reason", ""),
        )

    result.overall_comment = data.get("overall_comment", "")
    result.weighted_score = _compute_weighted(result.scores)
    return result


def _clamp(value: Any, lo: int = 0, hi: int = 10) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return 0


def _compute_weighted(scores: dict[str, DimensionScore]) -> float:
    total = 0.0
    for dim, weight in DIMENSION_WEIGHTS.items():
        total += scores.get(dim, DimensionScore(0, "")).score * weight
    return round(total, 2)
