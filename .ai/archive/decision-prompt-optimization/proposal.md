# Change Proposal: UPDATE_DECISION Prompt Evaluation And Self-Optimization

## Metadata

- Change ID: `decision-prompt-optimization`
- Type: `feature`
- Status: `approved`
- Spec impact: `update required`
- Verification profile: `full`
- Owner: `Codex`
- Related specs: `evaluation-workflow`, `owner-centered-memory`

## Summary

- Add a maintained evaluation and prompt-optimization workflow for
  `UPDATE_DECISION_SYSTEM_PROMPT`.
- Establish a dedicated decision-stage dataset, runner, and reporting model
  instead of relying only on coarse `owner_add` end-to-end outcomes.
- Add an offline self-optimization loop that generates candidate prompt
  variants, evaluates them on the full decision dataset, and promotes only
  candidates that beat the current baseline under explicit gates.

## Why Now

- The repository already has a mature STL prompt-optimization workflow and a
  unified eval runner, but the decision stage still lacks a dedicated
  optimization loop.
- `UPDATE_DECISION_SYSTEM_PROMPT` is currently short and under-specified
  relative to the complexity of ADD / UPDATE / DELETE / NONE choices.
- End-to-end `owner_add` eval can reveal that something is wrong, but it cannot
  localize whether the failure came from extraction, retrieval, decision, or
  execution. This makes prompt iteration slow and noisy.
- In repo reality, the decision LLM is not the update path for every memory
  family. Several stable families already bypass it via deterministic rules, so
  the dedicated dataset should prioritize the canonical memory shapes that
  still rely on `UPDATE_DECISION_SYSTEM_PROMPT` today.

## In Scope

- Define a dedicated decision-stage evaluation dataset and scoring model.
- Add a decision-stage runner that evaluates the prompt directly against
  `UPDATE_DECISION_SYSTEM_PROMPT` behavior.
- Add offline candidate generation and self-optimization tooling for decision
  prompt variants.
- Add reports and ranking criteria for deciding whether a prompt candidate
  should replace the current default.
- Keep the decision prompt source in `mind/prompts.py` as the maintained
  runtime default after a candidate is accepted.

## Out Of Scope

- Online or runtime self-modifying prompts.
- Automatic promotion of prompt variants without review.
- Retrieval changes, execution changes, or batch-decision architecture changes.
- STL extraction prompt work.
- Changing the public `Memory.add()` API.

## Proposed Changes

### 1. Add a dedicated decision dataset

- Create `tests/eval/decision_opt/cases/*.json` with structured decision cases.
- Each case will include:
  - `new_fact`
  - `existing_memories`
  - exact or acceptable actions
  - expected / acceptable target ids
  - text constraints for ADD / UPDATE
  - optional rationale expectations
- Cover easy, medium, and hard cases:
  - exact duplicates
  - semantic duplicates
  - refinement vs new-topic ambiguity
  - direct contradiction
  - preference evolution
  - multi-memory candidate confusion
  - invalid temp-id temptation
  - low-value facts that should become `NONE`

### 2. Add a direct decision runner

- Add `tests/eval/runners/eval_decision_ab.py` modeled after the STL A/B flow.
- Runner input:
  - control prompt text
  - candidate prompt text
  - one development model or separate model-per-arm
  - optional judge model
- Runner output:
  - per-case action results
  - JSON parse success
  - action exact accuracy
  - acceptable-action accuracy
  - id accuracy
  - text-constraint pass rate
  - optional LLM-as-judge quality score
  - summary report and machine-readable JSON artifact

### 3. Define a self-optimization loop

- Add an offline script that:
  1. reads the current prompt and recent failure cases
  2. asks a strong development model to propose one bounded prompt delta
  3. runs the full decision A/B evaluation against the control
  4. records the result and either rejects, folds, or promotes the candidate
- Candidate generation constraints:
  - change only one category per round
  - preserve required JSON schema
  - avoid anti-patterns already documented in the prompt-optimization skill
  - do not write directly into `mind/prompts.py` without passing gates

### 4. Add promotion gates

- A candidate prompt may be promoted only if all of these hold:
  - no regression in JSON parse success
  - no regression in acceptable-action accuracy
  - no regression in temp-id accuracy
  - positive gain in weighted composite score
  - no major regression on a protected common-case subset
- Promotion remains human-reviewed even when the candidate wins automatically.

## Reality Check

- Decision correctness is more ambiguous than STL extraction correctness. A
  single “golden” action is often too rigid, so the dataset must support
  acceptable action sets and text constraints rather than only one exact label.
- Full “self-optimization” should not mean the prompt edits itself in
  production. The safe interpretation is an offline optimization campaign with
  evaluation gates and human promotion.
- If we optimize only against end-to-end `owner_add`, the decision prompt will
  be confounded by extraction and retrieval noise. The better direction is a
  direct decision-stage harness first, then e2e validation second.
- The current fake backend is useful for deterministic tests, but it should not
  be the judge of prompt quality. Prompt optimization must use a real
  development model and optionally a separate judge model.
- A stronger, longer prompt is not automatically better. The STL skill’s
  anti-patterns apply here too: forceful language, negative examples, and
  overlong supplements can easily reduce decision quality.

## Acceptance Signals

- The repository has a maintained decision-stage dataset and runner.
- Engineers can evaluate control vs candidate decision prompts without going
  through full `owner_add` end-to-end runs.
- The optimization loop can generate candidate prompt variants and reject or
  promote them based on explicit gates.
- Reports make it clear which failure clusters improved and which regressed.
- Accepted prompt changes can still pass the existing `owner_add` regression
  path after decision-stage promotion.

## Verification Plan

- Use the `full` profile.
- Add pytest coverage for:
  - decision dataset loading and schema validation
  - decision runner parsing and score aggregation
  - candidate gating logic
- Run targeted manual or scripted prompt-eval smoke on a small decision case
  subset using a real model.
- Run `pytest tests/` after integrating any accepted prompt/runtime changes.
- Record generated reports and any promoted candidate comparison artifacts.

## Open Questions

- The first implementation will make the optimizer model configurable and keep
  the default unset, so repositories can choose a strong local development
  model without hard-coding a provider assumption.
- The first implementation will treat structured constraints as the required
  scoring path and LLM-as-judge as an optional overlay for higher-confidence
  campaign runs.
- “Self-optimization” is approved to run autonomously inside an offline
  campaign loop, including multi-round candidate generation and gated
  promotion, but it must not mutate production prompt text at runtime.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
