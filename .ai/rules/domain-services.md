# Rules: Domain Services (`mind/access/`, `mind/governance/`, `mind/capabilities/`, `mind/offline/`, `mind/workspace/`)

> Load this file when modifying domain-service modules.

---

## Scope

These modules contain business logic below the app layer and above the kernel.
They may orchestrate primitives, provider adapters, store operations, and
workspace composition, but they must stay independent from transport concerns.

## Rules

1. **No upward imports**: Domain services MUST NOT import `mind.app`,
   `mind.api`, `mind.mcp`, `mind.frontend`, `mind.cli`, or
   `mind.product_cli`.

2. **Keep entrypoints thin**: Public `service.py` methods should focus on
   orchestration, validation, and result assembly. Extract ranking, filtering,
   normalization, scoring, or payload-shaping logic into sibling modules before
   the service file turns into a monolith.

3. **Respect subdomain boundaries**:
   - `access/` owns retrieval, read, and workspace-selection behavior.
   - `governance/` owns plan/preview/execute flows and audit integrity.
   - `capabilities/` keeps provider-specific logic in adapter modules, not in
     generic service call sites.
   - `offline/` separates enqueue/scheduling from worker execution.
   - `workspace/` owns workspace composition policies, not transport behavior.

4. **Preserve deterministic service APIs**: Public service functions and result
   shapes should stay deterministic and testable without network calls. Mock
   only true external dependencies such as providers.

5. **Split by responsibility, not by helper count**: Preferred extraction
   boundaries are operation families (`read`, `retrieve`, `preview`, `execute`,
   `provider adapters`, `job handlers`) rather than random `utils.py` buckets.

6. **Add public-surface tests**: New domain-service behavior MUST be covered
   through the public service entrypoint or the closest stable public function,
   plus a regression test for the branch that motivated the change.

## Common Mistakes

- Letting `service.py` accumulate every branch for a subsystem.
- Putting provider-specific special cases into generic service orchestration.
- Mixing worker execution logic with scheduling code in `offline/`.
- Moving transport parsing concerns into domain modules.
