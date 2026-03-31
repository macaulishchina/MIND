# Spec: runtime-logging

### Purpose

- Define how runtime logging configuration applies across MIND entrypoints so ops logs and verbose detail follow config rather than caller-specific behavior.

### Requirements

### Requirement: Runtime Logging Configuration Applies Independently Of Caller

The system SHALL apply resolved logging configuration based on runtime config rather than on whether a particular caller happens to instantiate `Memory`.

#### Scenario: Direct LLM Utility Initializes Logging From Config

- WHEN a utility or runner performs direct LLM calls using a resolved `MemoryConfig`
- THEN the configured logging handlers and ops switches are applied before the call so ops logs follow the active config

#### Scenario: Ops Switches Refresh On Reconfiguration

- WHEN runtime logging configuration is applied more than once in the same process
- THEN the effective ops switches and verbosity reflect the most recent configuration instead of keeping stale values from the first initialization

### Requirement: Verbose Ops Detail Is Controlled Only By Logging Config

The system SHALL emit verbose ops detail whenever `logging.verbose=true` and the relevant log category is enabled, without requiring caller-specific opt-in flags.

#### Scenario: Verbose LLM Detail Appears For Direct Utility Calls

- WHEN `logging.verbose=true` and a direct LLM utility call succeeds
- THEN the logs include the summary `🧠 [LLM]` line and the subordinate verbose prompt/output lines for that call

#### Scenario: Disabled Category Still Suppresses Its Logs

- WHEN an ops category such as `logging.ops_llm` is false
- THEN the system suppresses that category's logs even if `logging.verbose=true`
