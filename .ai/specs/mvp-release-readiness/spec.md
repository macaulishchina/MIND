# Spec: mvp-release-readiness

### Purpose

- Define the maintained MVP release-readiness baseline so docs, tests, and
  acceptance expectations match the current implemented architecture.

### Requirements

### Requirement: Maintained MVP Entry Documentation

The repository SHALL document MVP quickstart and evaluation entrypoints using
maintained commands that exist in the current codebase.

#### Scenario: README Uses Maintained Eval Runner

- WHEN a developer follows the MVP evaluation guidance in `README.md`
- THEN the documented owner-add evaluation command uses the maintained unified
  eval runner
- AND it does not reference removed or missing scripts

### Requirement: MVP Acceptance Baseline Is Documented

The repository SHALL maintain one durable MVP acceptance baseline that matches
the implemented architecture.

#### Scenario: MVP Docs Describe Current Baseline

- WHEN a developer reads the MVP definition and evaluation materials
- THEN they can see the maintained public API surface, acceptance signals, and
  known MVP limitations
- AND those materials describe the current STL-native architecture rather than
  an obsolete pipeline

### Requirement: MVP Public API Smoke Coverage Exists

The repository SHALL provide at least one focused automated smoke test for the
maintained MVP public API surface.

#### Scenario: Smoke Test Exercises Public CRUD Path

- WHEN the pytest suite runs
- THEN at least one automated test exercises the public `Memory` API methods
  needed for MVP operation
- AND that smoke path includes add/search/read/update/delete/history behavior

### Requirement: Deleted Memories Stay Out Of The Public Search Surface

The repository SHALL keep logically deleted memories out of the maintained
public search surface used by the MVP API.

#### Scenario: Delete Removes A Memory From Public Search Results

- WHEN a memory is logically deleted through the public API
- THEN `get_all()` no longer returns it
- AND public `search()` does not re-surface the same fact through a lower-level
  STL-only result shape

### Requirement: MVP Live Owner-Add Baseline Is Archived

The repository SHALL maintain point-in-time live `owner_add` evaluation
evidence for the MVP using the maintained real-model runtime path, while
keeping deterministic pytest coverage as the day-to-day regression gate.

#### Scenario: Live Owner-Add Baseline Can Be Reviewed And Reproduced

- WHEN a developer needs the current MVP `Memory.add()` behavior under real
  models
- THEN the repository points to an archived or tracked `owner_add` report
  produced by the maintained unified eval runner with a real-model config such
  as `mind.toml`
- AND that evidence records the command/config context, metric outcomes, and
  failed cases
- AND MVP-facing docs explain that the live baseline is point-in-time evidence
  rather than a deterministic CI requirement
