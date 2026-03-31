# Spec: memory-add-extraction

## REMOVED Requirements

### Requirement: Extraction Evaluation Dataset Topology

The repository SHALL maintain curated extraction evaluation datasets as a compact general regression set plus a dedicated relation-focused set.

#### Scenario: Default Regression Discovery Uses Curated Top-Level Datasets

- WHEN `tests/eval/runners/eval_extraction.py` runs without an explicit `--dataset` path
- THEN it evaluates the maintained top-level curated extraction datasets and does not rely on the old easy/medium/hard/tricky plus standalone black-box topology

#### Scenario: Curated General Extraction Dataset Exists

- WHEN the repository defines its general extraction regression dataset
- THEN that dataset is a single curated JSON file with 100 cases assembled from the previous extraction and black-box sources, with low-value trivial cases removed

#### Scenario: Curated Relationship Extraction Dataset Exists

- WHEN the repository defines its relationship-focused extraction regression dataset
- THEN that dataset is a separate 100-case JSON file dedicated to relation-bearing inputs and coverage

### Requirement: Extraction Evaluation Supports Relationship Signals

The extraction evaluation runner SHALL support optional relationship-aware annotations while remaining compatible with legacy fact-only datasets.

#### Scenario: Legacy Extraction Dataset Still Runs

- WHEN an extraction dataset uses only the pre-existing fact-oriented fields
- THEN `tests/eval/runners/eval_extraction.py` evaluates it without requiring any relationship annotations

#### Scenario: Relation-Aware Extraction Dataset Reports Relationship Metrics

- WHEN an extraction dataset includes relationship-aware expectations
- THEN `tests/eval/runners/eval_extraction.py` scores those relationship expectations from extracted fact text and reports relationship-oriented metrics alongside the existing extraction metrics
