# Check: spec-consistency

## Purpose

Verify that the source-of-truth spec, change-local spec delta, proposal, and
tasks do not contradict each other.

## When To Use

- any change with `Spec impact: update required`
- any feature profile
- any full profile

## Pass Criteria

- The proposal describes the same behavioral intent as the spec delta.
- Tasks are sufficient to implement the intended requirement changes.
- No source-of-truth spec was prematurely edited during drafting.

## Acceptable Evidence

- manual comparison notes
- linked review comments
- automated consistency tooling if added later
