# Rules: Primitives Layer (`mind/primitives/`)

> Load this file when modifying anything under `mind/primitives/`.

---

## Scope

Primitives are the atomic operations of MIND. They sit between the kernel
(storage) and the application services (orchestration).

## Key Files

| File | Purpose |
|------|---------|
| `contracts.py` | All request/response Pydantic models, enums, `ContractModel` base |
| `service.py` | `PrimitiveService` — orchestrates all primitive calls |
| `runtime.py` | `PrimitiveRuntime` — validation, transactions, telemetry |

## Rules

1. **Contract-first**: Define the request/response models in `contracts.py`
   BEFORE writing the implementation in `service.py`.

2. **Add to PrimitiveName**: Every new primitive MUST have a member in the
   `PrimitiveName` enum.

3. **ContractModel inheritance**: All request/response types MUST inherit
   from `ContractModel` (which enforces `extra="forbid"`, `frozen=True`).

4. **Budget tracking**: Every primitive call MUST record a `BudgetEvent`
   and a `PrimitiveCallLog`.

5. **Telemetry**: Use the injected `TelemetryRecorder` — never create your own.

6. **Error types**: Use `PrimitiveErrorCode` enum for error conditions.
   New error codes MUST also be mapped in `mind/app/errors.py` → `AppErrorCode`.

7. **Pure logic**: Primitives MUST NOT call transport or app-layer code.
   They only call kernel (store) methods.

8. **Deterministic in tests**: Primitive logic must work without any LLM
   provider. Use the `deterministic` / `stub` provider for tests.

## Common Mistakes

- Adding a primitive but forgetting to add it to `PrimitiveName` enum.
- Forgetting to map a new `PrimitiveErrorCode` to `AppErrorCode`.
- Calling app-layer code from within a primitive.
