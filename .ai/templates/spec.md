# Spec: <capability-name>

Use this template in two modes:

- In `.ai/specs/<capability>/spec.md`, write the current approved truth.
- In `.ai/changes/<change-id>/specs/<capability>/spec.md`, write only the
  proposed delta for this change.

## Source-Of-Truth Format

### Purpose

- Describe the capability in one short paragraph.

### Requirements

### Requirement: <requirement-name>

The system SHALL <required behavior>.

#### Scenario: <scenario-name>

- WHEN <trigger or precondition>
- THEN <observable outcome>

## Change-Delta Format

For change-local specs, replace the sections above with one or more of the
following headings:

- `## ADDED Requirements`
- `## MODIFIED Requirements`
- `## REMOVED Requirements`

Inside each heading, use the same `Requirement` and `Scenario` structure.
For modified requirements, include the complete updated requirement text.
