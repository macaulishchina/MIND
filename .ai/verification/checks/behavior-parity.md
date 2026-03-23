# Check: behavior-parity

## Purpose

Verify that a refactor or internal change preserved the intended behavior.

## When To Use

- refactor profile
- full profile when behavior preservation is an explicit goal

## Pass Criteria

- No unintended behavior change is introduced.
- Any intentionally changed behavior is called out and no longer treated as pure
  parity work.
- The available evidence supports the parity claim.

## Acceptable Evidence

- before/after reasoning
- focused test results once tests exist
- manual scenario walkthroughs
