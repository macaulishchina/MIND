# Rules: Transport & Experience (`mind/mcp/`, `mind/frontend/`, `mind/cli.py`, `mind/product_cli.py`)

> Load this file when modifying transport-layer modules outside REST API.

---

## Scope

These modules are the user-facing edge of the system: MCP tools, frontend
experience adapters, and CLI commands. They translate external inputs into app
service requests and project app results back into transport-specific outputs.

## Rules

1. **Go through app services**: Transport modules MUST call
   `mind/app/services/` or `AppServiceRegistry` surfaces. They MUST NOT call
   primitives, domain services, or store methods directly.

2. **Keep business logic out of transport**: Parsing, validation, projection,
   formatting, and transport-specific errors belong here. Ranking logic,
   retrieval policy, provider selection policy, and persistence behavior do
   not.

3. **Preserve execution context**: Principal, session, namespace, policy, and
   provider-selection data must not be silently dropped when building
   `AppRequest`.

4. **Treat public contracts as stable**: Changes to CLI command behavior, MCP
   tool schema, or frontend request/response shape require matching tests and
   documentation updates.

5. **Do not grow CLI monoliths by default**: `mind/cli.py` and
   `mind/product_cli.py` are already oversized. Prefer extracting command
   groups, formatters, API clients, or shared option builders into sibling
   modules instead of appending another large block.

## Common Mistakes

- Calling a primitive or store directly from a tool or command handler.
- Embedding domain decision trees in CLI/MCP/frontend glue code.
- Forgetting to pass provider-selection or policy context through transport.
- Adding a new public command/tool without docs and tests.
