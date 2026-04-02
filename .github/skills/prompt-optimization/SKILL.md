---
name: prompt-optimization
description: >
  **WORKFLOW SKILL** — Plan, execute, and iterate on LLM prompt optimization
  campaigns with structured evaluation. USE FOR: system prompt tuning for any
  LLM task; building evaluation datasets with golden references; running
  LLM-as-judge quality scoring; cross-model comparison under production
  constraints (timeout, cost); composite ranking with speed/quality/reliability
  trade-offs. DO NOT USE FOR: one-off prompt writing without iteration;
  application-level debugging; model fine-tuning.
---

# Prompt Optimization Skill

Structured methodology for iterating on LLM system prompts and evaluating
them across models under production constraints.

## When to Use

- Optimizing a system prompt for a specific extraction / generation task
- Building or extending an evaluation dataset with golden references
- Running cross-model comparisons with speed, quality, and reliability metrics
- Establishing model recommendations for production deployment

## Phase 1 — Baseline & Seed Cases

1. **Lock the grammar/schema** — Define the exact output format the LLM must
   produce. Document every construct, valid types, and forbidden patterns.
2. **Write 5–10 seed cases** — Cover the most common scenarios plus 2–3 edge
   cases (corrections, negations, long input). Each case needs:
   - Input (conversation / text)
   - `golden_stl` (human-written reference output)
3. **Pick a development model** — Use a high-quality model (e.g.,
   claude-opus-4-6) as the optimization target. Speed doesn't matter here.
4. **Establish baseline score** — Run all seed cases through the current
   prompt. Record average score for comparison.

## Phase 2 — Iterative Prompt Optimization

Repeat in rounds (typically 6–8 rounds to converge):

1. **Analyze failures** — For each case scored below target, identify the root
   cause:
   - Missing rule? → Add an explicit rule.
   - Ambiguous wording? → Rewrite to be unambiguous.
   - Conflicting rules? → Resolve with priority or mutual exclusion.
2. **Apply ONE category of fix per round** — Avoid changing too many things at
   once. Typical fix categories:
   - Add/refine a rule
   - Remove redundant text
   - Restructure sections
   - Add a minimal canonical example
3. **Re-evaluate on ALL cases** — Never evaluate on just the fixed case. Watch
   for regressions.
4. **Record the delta** — Note what changed and the score impact.

### Prompt Engineering Principles

- **Rules > Examples** — Each desired behavior should be an explicit rule, not
  implied by examples. Examples illustrate; rules constrain.
- **Prohibitions > Permissions** — "NEVER output X" is stronger than "only
  output Y". LLMs respond better to explicit bans.
- **Mutual exclusion must be stated** — If two constructs are mutually
  exclusive, say so explicitly. Don't rely on the model inferring it.
- **Structured sections** — Group rules by topic with clear headers. The model
  processes structured text more reliably than a wall of rules.
- **Size sweet spot** — For extraction tasks, 80–120 lines / 4–6 KB is
  typically optimal. Shorter loses rules; longer dilutes attention.
- **Canonical example at the end** — One short, correct example at the bottom
  anchors the output format.

### Prompt Engineering Anti-Patterns

These patterns were empirically validated to **hurt** quality. Avoid them.

- **"CRITICAL" / forceful language backfires** — Words like "CRITICAL",
  "EXTREMELY IMPORTANT", or "YOU MUST ABSOLUTELY" cause weaker models
  (e.g., deepseek-v3.2) to over-react, producing cautious or degenerate
  output. Use calm, declarative rules instead.
- **Negative examples act as priming** — Showing `✗ bad output` teaches the
  model what bad output looks like, then it imitates it. Prefer showing only
  the correct form. If you must show a wrong example, keep it minimal and
  clearly label it as wrong.
- **Naming bad patterns summons them** — "Do NOT invent predicates like
  `symptom`, `workplace`, `stress`" primes the model to produce exactly those
  predicates. Instead state the positive rule: "Use ONLY seed predicates."
- **Supplement ≠ always better** — Appending extra guidance increases token
  count and dilutes attention. A shorter, tighter base prompt often outperforms
  a longer base+supplement. Test with A/B before committing.
- **Worked examples have diminishing returns** — 1 canonical example helps.
  3+ worked examples for edge cases add bulk that drowns out rules. Prefer
  concise rules over multiple scenario walk-throughs.

## Phase 3 — A/B Testing Prompt Variants

When evaluating whether an optional supplement, restructuring, or alternative
prompt version improves quality, run a controlled A/B test.

### 3.1 A/B Runner Design

- **Arm A** = current prompt (control). **Arm B** = candidate prompt (treatment).
- Both arms receive the same input and model configuration.
- Use `ThreadPoolExecutor(max_workers=2)` to run both arms in parallel per
  case — this halves wall clock time without cross-contamination.
- Add error handling (try/except) around LLM calls so a single timeout or
  error doesn't crash the entire run.

### 3.2 Three Evaluation Modes

Choose based on cost/accuracy trade-off:

| Mode | Cost | Accuracy | When to use |
|------|------|----------|-------------|
| **Parse-only** | Free | Low | Quick iteration; checks format compliance only |
| **Structured** | Free | Medium | When cases have `expected_refs`/`expected_statements` |
| **LLM-as-judge** | $$ | High | Final validation; quantitative comparison |

During iterative development, use parse-only (`--skip-judge`) for fast
feedback (~15s/case). Reserve LLM-as-judge for final validation runs.

### 3.3 What to Measure

Track these metrics separately — they can contradict each other:

- **Win rate** — How many cases does each arm win? (majority vote)
- **Average score** — Judge-assigned quality. Higher is better.
- **Parse failures** — Format violations that cause data loss. In production,
  a parse failure is worse than a lower score.
- **Statement count** — Rough proxy for completeness. Under-extraction
  (too few) and over-extraction (too many) are both problems.

> **Key insight**: Win rate and average score can disagree. Arm B might win
> fewer cases overall but have a higher average because it dominates a few
> edge cases by large margins. Always look at both metrics.

### 3.4 Iteration Discipline

1. Change ONE thing per iteration. Run all cases. Compare.
2. If a change helps edge cases but hurts common cases, **don't ship it**.
   Instead, try to fold the specific improvement into the base prompt.
3. When a supplement's gains are concentrated in specific scenarios
   (e.g., correction, retraction), the better strategy is to strengthen those
   rules in the base prompt rather than adding an optional supplement.
4. After 3–4 iterations without improvement, the prompt has likely converged.
   Stop iterating.

### 3.5 Decision Framework: Ship or Fold?

After A/B testing, choose one of:

| Outcome | Action |
|---------|--------|
| B wins on score AND format | Ship B as new default |
| B wins on score, loses on format | **Fold** B's best rules into base prompt |
| B loses on both | Discard B |
| Mixed / inconclusive | Run more cases or try a smaller delta |

"Fold" means merging the effective subset of the variant back into the base
prompt — you get the quality benefit without the format cost of extra length.

## Phase 4 — Expand the Evaluation Dataset

After the prompt stabilizes (score improvement <0.2 per round):

1. **Add 10+ diverse cases** covering:
   - Long conversations (30–50 turns) with simple facts
   - Short conversations (5–10 turns) with complex logic
   - Domain-specific scenarios (health, travel, tech, food, family, etc.)
   - Edge cases: ambiguity, multi-event, corrections chained with other facts
2. **Write golden references for all new cases** — Ensure they follow the
   optimized prompt's rules exactly.
3. **Re-evaluate** — The new expanded set may reveal weaknesses.

## Phase 5 — Cross-Model Comparison

### 5.1 Speed Probe

Before full evaluation, run a quick probe (2–3 cases) on each candidate model:

- **Eliminate models with avg latency > 2× your timeout** — They'll mostly
  time out in the full run.
- Record probe results for reference.

### 5.2 Round 1 — Baseline (No Timeout)

- Run all cases on all remaining models without timeout.
- Collect: success rate, average/median/min/max latency, total statements.
- Purpose: pure performance baseline; identify which models are viable.

### 5.3 Round 2 — Production Constraints

- Apply a hard per-request timeout (e.g., 10s) matching production SLA.
- Use `ThreadPoolExecutor` with inner timeout for reliable enforcement:
  ```python
  with ThreadPoolExecutor(max_workers=1) as pool:
      fut = pool.submit(call_llm, ...)
      result = fut.result(timeout=TIMEOUT_S)
  ```
- Collect: success/timeout/error counts, latency stats, statement counts.

### 5.4 Quality Evaluation (LLM-as-Judge)

Use a fast, cheap model (e.g., gpt-5.4-nano) as the judge:

1. **Define scoring dimensions** — Typically 5–8 dimensions relevant to the
   task. Each dimension gets a weight summing to 1.0.
2. **Judge prompt** — Provide:
   - Task description and output format spec
   - The original input
   - The golden reference
   - The actual output
   - Scoring rubric (0–10 per dimension with descriptions)
3. **Parse structured scores** — Judge must output JSON with per-dimension
   scores and rationale.
4. **Compute weighted average** per case, then mean across cases = model score.

### 5.5 Composite Ranking

Combine metrics with a weighted formula. Suggested weights:

| Metric | Weight | Description |
|--------|--------|-------------|
| speed | 25% | Inverse of average latency (min-max normalized) |
| quality | 35% | LLM-as-judge weighted score (min-max normalized) |
| reliability | 25% | Success rate = ok / total |
| throughput | 15% | Statements per second (min-max normalized) |

Adjust weights based on production priorities (latency-sensitive → increase
speed weight; accuracy-critical → increase quality weight).

## Phase 6 — Recommendation

Classify models into tiers:

| Tier | Criteria |
|------|----------|
| **S** | Best balance of reliability + speed + acceptable quality. Production default. |
| **A** | High quality or good balance. Use for quality-sensitive or batch workloads. |
| **B** | Acceptable fallback. One metric is notably weak. |
| **C** | Marginal. Only for specific niche use. |
| **D** | Not recommended. Failed on reliability or quality. |

## Artifacts Checklist

At the end of a campaign, ensure these exist:

- [ ] Optimized system prompt in source code
- [ ] Evaluation cases with golden references (`cases/*.json`)
- [ ] A/B test runner with parallel extraction and error handling
- [ ] A/B test reports (JSON) with per-case scores and parse failure counts
- [ ] Judge implementation with defined dimensions and weights
- [ ] Round 1 results (speed baseline)
- [ ] Round 2 results (production constraints + quality)
- [ ] Composite ranking data
- [ ] Summary report (REPORT.md)

## Adaptation Notes

This skill is designed to be task-agnostic. When reusing for a different
prompt optimization campaign:

- **Phase 1**: Replace the grammar/schema with your task's output specification.
- **Phase 3**: Design A/B tests for your specific prompt variants. The runner
  pattern (parallel arms, error handling, three eval modes) is reusable.
- **Phase 4**: Design cases for your domain, not STL-specific scenarios.
- **Phase 5.4**: Redefine judge dimensions to match your task's quality axes.
- **Weights**: Tune the composite formula to your production priorities.
