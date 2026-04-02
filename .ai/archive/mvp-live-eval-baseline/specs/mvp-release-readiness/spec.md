# Spec: mvp-release-readiness

## ADDED Requirements

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
