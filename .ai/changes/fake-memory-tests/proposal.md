# Change Proposal: Fake Memory Tests

## Metadata

- Change ID: `fake-memory-tests`
- Type: `refactor`
- Status: `implementing`
- Spec impact: `none`
- Verification profile: `refactor`
- Owner: `GitHub Copilot`
- Related specs: `none`

## Summary

- Replace live LLM and embedding calls in memory tests with deterministic fake backends.
- Keep the add/search/update pipeline behavior under test without consuming tokens or requiring API keys.

## Why Now

- Current memory tests depend on real API credentials and external model behavior.
- This makes tests slower, more expensive, and less deterministic than necessary.
- Recent Memory lifecycle refactor benefits from fast local verification.

## In Scope

- Add fake LLM and fake embedding backends.
- Wire factories to support fake protocols.
- Switch memory tests to constructor-time fake config.
- Keep assertions focused on behavior feedback from the memory pipeline.

## Out Of Scope

- Replacing all integration tests with fakes across the repository.
- Changing production provider behavior.
- Adding broad benchmark or evaluation infrastructure.

## Proposed Changes

- Introduce deterministic fake implementations for `BaseLLM` and `BaseEmbedding`.
- Use simple heuristic extraction/decision behavior to cover existing test scenarios.
- Use deterministic embeddings with light semantic concept expansion so search-related tests still verify meaningful retrieval.
- Remove API-key gating from the core memory test file.

## Reality Check

- A fake backend can hide provider-specific issues, so this should not be treated as real provider integration coverage.
- The fake decision logic must be simple and explicit; if it becomes too clever, the tests stop reflecting product behavior and start validating the fake.
- The right balance is deterministic behavioral coverage for pipeline orchestration, while leaving true provider validation to optional live tests.

## Acceptance Signals

- `tests/test_memory.py` runs without real API keys.
- No real LLM or embedding network calls are made in that suite.
- Existing memory pipeline assertions still pass with deterministic feedback.

## Verification Plan

- Use the `refactor` profile.
- Run focused pytest on `tests/test_memory.py` and `tests/test_storage.py`.
- Review factories and tests manually to confirm fake protocols are only used when explicitly configured.

## Open Questions

- None blocking.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
