# Verification Report: llm-stage-config-audit

## Metadata

- Change ID: `llm-stage-config-audit`
- Verification profile: `full`
- Status: `complete`
- Prepared by: `Codex`

## Checks Run

### `workflow-integrity`

- Result: `pass`
- Evidence:
  - Change artifacts created under `.ai/changes/llm-stage-config-audit/`
  - Proposal approved before implementation
  - Living specs updated after implementation
- Notes:
  - `.human/` handbook docs were reviewed; no workflow-handbook update was needed because this change altered product/runtime behavior, not the `.ai/.human` workflow itself.

### `change-completeness`

- Result: `pass`
- Evidence:
  - Legacy fact extraction / normalization helpers removed from `mind/memory.py`
  - Legacy prompt branches removed from `mind/prompts.py` and `mind/llms/fake.py`
  - Default TOML files and README now expose only STL-native stage overrides
- Notes:
  - Outdated notebook/doc/test assets tied to the removed helper path were deleted.

## Additional Checks

### `stage-usage-audit`

- Result: `pass`
- Evidence:
  - `rg -n "_extract_facts|_normalize_single_fact|_process_fact|FACT_EXTRACTION_SYSTEM_PROMPT|FACT_NORMALIZATION_SYSTEM_PROMPT|llm\\.extraction|llm\\.normalization" . --glob '!**/.git/**' --glob '!**/.ai/archive/**'`
- Notes:
  - Remaining matches are limited to intentional deprecation assertions/tests and `llm.extraction_temperature`, which now feeds STL extraction temperature fallback.

### `config-runtime-alignment`

- Result: `pass`
- Evidence:
  - `python - <<'PY' ... ConfigManager('mind.toml').get() ... print(sorted(cfg.llm_stages)) ... PY` -> `stages []`
  - `python - <<'PY' ... Memory(_eval_config(ConfigManager('mind.toml').get(), ...)) ... print(memory._stl_extraction_temperature()) ... PY` -> initializes successfully with `vector_store qdrant`
- Notes:
  - The maintained runtime now recognizes only `llm.stl_extraction` and `llm.decision` as active stage overrides.

### `behavior-regression`

- Result: `pass`
- Evidence:
  - `pytest -q tests/test_batch_config.py tests/test_fake_llm.py tests/test_memory.py tests/test_eval_owner_centered_add.py tests/test_memory_helpers.py` -> `38 passed`
  - `pytest -q tests` -> `181 passed`
- Notes:
  - Test count decreased because legacy extraction-specific tests were intentionally removed and replaced with current helper coverage.

### `doc-config-alignment`

- Result: `pass`
- Evidence:
  - Reviewed and updated `README.md`, `tests/eval/README.md`, `mind.toml`, `mindt.toml`, and `mind.toml.example`
- Notes:
  - Default config files no longer advertise removed `llm.extraction` / `llm.normalization` stage blocks.

## Residual Risk

- Any private/local scripts outside the repository that still call the deleted legacy helper APIs will need to move to STL-native debugging paths.

## Summary

- The selected `full` verification profile is satisfied.
- The repository now exposes a cleaned LLM stage configuration surface aligned with the STL-native business path.
