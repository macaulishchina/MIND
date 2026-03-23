# Verification Framework

This directory defines the repository's verification model.
It describes what must be validated for a change, without requiring any
particular script or toolchain runner.

## Layers

- `policy.md`: when verification is required and how to choose a profile
- `profiles/`: reusable verification bundles such as `quick` or `full`
- `checks/`: reusable check definitions with intent and success criteria
- `templates/`: copyable reporting artifacts for change-local verification

## Core Idea

Verification is a workflow concern, not a script name.
When automation exists later, scripts can execute these checks, but the checks
and profiles should still make sense even when verification is manual.

## Usage

1. Read `policy.md`.
2. Select a verification profile for the change.
3. Use the profile to determine which checks must be satisfied.
4. Record the result in a change-local verification report.
