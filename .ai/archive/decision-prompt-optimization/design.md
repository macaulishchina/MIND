# Design: UPDATE_DECISION Prompt Evaluation And Self-Optimization

## Goal

Build a disciplined offline optimization loop for
`UPDATE_DECISION_SYSTEM_PROMPT`, using the existing prompt-optimization skill as
the method baseline and adapting it to the ambiguity of decision-stage labels.

## Why Decision Prompt Needs A Different Design

STL extraction optimization works well with golden outputs because the target is
mostly structural and explicit. Decision prompt optimization is harder because:

- more than one action can sometimes be acceptable
- `UPDATE` text quality matters, not just action label
- temp-id accuracy matters independently from action correctness
- a prompt can “win” on hard edge cases while hurting common cases

So the decision harness should treat correctness as a combination of:

- exact metrics for rigid constraints
- acceptable sets for ambiguous outcomes
- optional judge scoring for nuanced text quality

One more repo-reality constraint matters here: the current runtime only calls
the decision LLM for the residual `llm` update mode after deterministic
single-value / set-value / append-only branches have been handled. The first
seed dataset therefore should focus on canonical memory strings that still
exercise this maintained decision path, rather than pretending the decision
prompt owns every update case in `Memory.add()`.

## Evaluation Model

### 1. Deterministic Constraints First

These should be mandatory and machine-scored:

- JSON parse success
- action exact match
- action acceptable match
- temp-id correctness for UPDATE / DELETE
- text constraint pass for ADD / UPDATE

### 2. Optional Judge Layer Second

Add LLM-as-judge only after the deterministic layer exists. Judge dimensions:

- action_reasonableness
- contradiction_handling
- update_vs_add_choice
- id_reference_correctness
- updated_text_quality
- low_value_fact_suppression
- format_compliance

Judge should be advisory but included in the composite score.

## Dataset Design

Create a new directory:

```text
tests/eval/decision_opt/cases/
```

Case shape:

```json
{
  "id": "dec-001",
  "description": "preference evolution should prefer update",
  "new_fact": "[self] preference:like=americano",
  "existing_memories": [
    {"id": "0", "content": "[self] preference:like=black coffee"}
  ],
  "expected_action": "UPDATE",
  "acceptable_actions": ["UPDATE"],
  "expected_id": "0",
  "text_must_contain": ["americano"],
  "text_must_not_contain": ["black coffee"],
  "difficulty": "medium",
  "cluster": "preference_evolution"
}
```

Recommended case clusters:

- exact_duplicate
- semantic_duplicate
- refinement_update
- contradiction_delete
- preference_evolution
- low_value_none
- unrelated_add
- multi_candidate_disambiguation
- id_integrity
- ambiguous_but_acceptable

## Runner Design

Add:

```text
tests/eval/runners/eval_decision_ab.py
```

Runner responsibilities:

1. load decision cases
2. render user payload with temporary ids and new fact
3. run control and candidate prompts in parallel per case
4. parse JSON responses safely
5. score both arms
6. optionally call judge on each arm
7. emit JSON and markdown summaries

Key outputs:

- per-case arm result
- per-metric aggregate
- win/loss/tie summary
- regression list on protected cases

## Self-Optimization Loop

Add:

```text
tests/eval/decision_opt/optimize_decision_prompt.py
```

Loop per round:

1. load current prompt
2. load previous report and identify worst clusters
3. ask optimizer model for one bounded candidate delta
4. run full A/B on all decision cases
5. compare against promotion gates
6. classify result:
   - promote
   - fold partial rules into base
   - reject
7. record artifacts

The optimizer model should receive:

- current prompt
- top failure cases
- anti-pattern reminders from the prompt-optimization skill
- a hard instruction to change only one category

## Promotion Policy

Candidate promotion requires:

- parse_success not lower than control
- acceptable_action_accuracy not lower than control
- id_accuracy not lower than control
- weighted score improves
- protected common-case cluster does not regress beyond threshold

Suggested first composite score:

- acceptable_action_accuracy: 30%
- exact_action_accuracy: 15%
- id_accuracy: 20%
- text_constraint_pass: 15%
- parse_success: 10%
- judge_quality: 10%

## Recommended Rollout Sequence

1. Build 10–15 seed decision cases and baseline report
2. Add direct decision A/B runner
3. Run manual optimization rounds with one strong dev model
4. Expand to 30+ cases after prompt stabilizes
5. Add self-optimization script with gated candidate generation
6. Validate promoted prompt with existing `owner_add` end-to-end eval

## First Implementation Cut

Keep the first slice intentionally narrow:

- no automatic prompt promotion
- no runtime changes
- no architecture changes to retrieval/decision execution
- direct prompt evaluation only

This keeps the campaign focused on one variable:
`UPDATE_DECISION_SYSTEM_PROMPT`.
