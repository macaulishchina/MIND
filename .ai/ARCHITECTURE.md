# MIND Architecture Decision Record

> Auto-extracted from codebase on 2026-03-13. Keep in sync with code.

---

## 1. System Layers

```
┌─────────────────────────────────────────────────────┐
│  Transport Layer                                     │
│  mind/api/  │  mind/mcp/  │  mind/cli.py  │ frontend│
├─────────────────────────────────────────────────────┤
│  Application Service Layer                           │
│  mind/app/services/  +  mind/app/registry.py         │
├─────────────────────────────────────────────────────┤
│  Domain Service Layer                                │
│  mind/access/  mind/governance/  mind/capabilities/  │
│  mind/offline/                                       │
├─────────────────────────────────────────────────────┤
│  Primitives Layer                                    │
│  mind/primitives/                                    │
├─────────────────────────────────────────────────────┤
│  Kernel Layer                                        │
│  mind/kernel/  (store, schema, retrieval, provenance)│
└─────────────────────────────────────────────────────┘
```

### Call Direction
- Transport → App Services → Domain Services → Primitives → Kernel
- **Never** upward. **Never** skip layers (transport must not call primitives directly).

---

## 2. Key Patterns

### 2.1 Dependency Injection via Composition Root

**File**: `mind/app/registry.py`

`AppServiceRegistry` is a `@dataclass` holding every service as a field. The
`build_app_registry()` context manager is the only place where services are
instantiated and wired together.

```python
@dataclass
class AppServiceRegistry:
    store: MemoryStore
    config: ResolvedCliConfig
    primitive_service: PrimitiveService
    access_service: AccessService
    # ... all services ...
```

**Why**: Single place to understand all dependencies. Easy to test (swap fields).

### 2.2 Request/Response Envelope

**Files**: `mind/app/contracts.py`, `mind/app/context.py`

Every app service method signature:
```python
def method_name(self, req: AppRequest) -> AppResponse:
```

- `AppRequest.input` is a `dict[str, Any]` carrying operation-specific data.
- `AppResponse.status` is `AppStatus` enum (ok/error/rejected/not_found/unauthorized).
- `AppResponse.result` carries the successful result payload.
- `AppResponse.error` is an `AppError` with typed `AppErrorCode`.

### 2.3 Execution Context Resolution

**File**: `mind/app/context.py`

Each request carries optional contexts:
- `PrincipalContext` — who is calling (user/service/system/api_key)
- `SessionContext` — conversation session
- `NamespaceContext` — data isolation boundary
- `ExecutionPolicy` — budget limits, capabilities, dev mode
- `ProviderSelection` — LLM provider/model choice

These are resolved via `resolve_execution_context()` into a
`PrimitiveExecutionContext` for the primitives layer.

### 2.4 Error Mapping

**File**: `mind/app/errors.py`

Domain exceptions (`PrimitiveError`, `GovernanceServiceError`, `StoreError`,
etc.) are mapped to `AppErrorCode` by `map_domain_error()`. This keeps domain
layers independent of the app-layer error vocabulary.

### 2.5 Store Protocol Abstraction

**File**: `mind/kernel/store.py`

`MemoryStore` is a `typing.Protocol` — not an ABC. Two implementations:
- `SQLiteMemoryStore` — in-process, used for dev/test
- `PostgresMemoryStore` — production, with pgvector support

Both implement the full protocol. Any new store method MUST be added to the
protocol and both implementations.

### 2.6 Primitive Runtime

**File**: `mind/primitives/runtime.py`, `mind/primitives/service.py`

`PrimitiveService` orchestrates all primitive calls:
1. Validates capabilities and budget constraints.
2. Opens a transaction (`store.transaction()`).
3. Executes the primitive logic.
4. Records telemetry via `TelemetryRecorder`.
5. Returns a typed `PrimitiveResult`.

### 2.7 Capability Provider Adapters

**Files**: `mind/capabilities/service.py`, `mind/capabilities/claude_adapter.py`

Unified adapter protocol for LLM providers (Claude, OpenAI, Gemini, Deterministic stub).
`CapabilityService` resolves the provider from config and delegates calls.

### 2.8 Offline Job System

**Files**: `mind/offline/scheduler.py`, `mind/offline/service.py`

Background jobs (reflection, schema promotion, maintenance) are scheduled into
the store and executed by a polling worker. `OfflineJobScheduler` enqueues,
`OfflineMaintenanceService` executes.

### 2.9 Governance Control Plane

**Files**: `mind/governance/service.py`, `mind/governance/gate.py`

Conceal/erase workflows follow plan → preview → execute stages.
Full audit trail via `GovernanceAuditRecord`. Provenance integrity checks
prevent orphaned or duplicate records.

---

## 3. Module Dependency Map

```
mind/api/*          → mind/app/services/*        (always)
mind/mcp/*          → mind/app/services/*        (always)
mind/cli.py         → mind/app/registry.py       (always)
mind/app/services/* → mind/primitives/service.py (for ingest/query/feedback)
mind/app/services/* → mind/access/service.py     (for access)
mind/app/services/* → mind/governance/service.py (for governance)
mind/app/services/* → mind/offline/service.py    (for jobs)
mind/primitives/*   → mind/kernel/store.py       (always)
mind/access/*       → mind/kernel/store.py       (always)
mind/governance/*   → mind/kernel/store.py       (always)
mind/offline/*      → mind/primitives/service.py (always)
```

---

## 4. Configuration System

**File**: `mind/cli_config.py`

Profiles: `AUTO`, `SQLITE_LOCAL`, `POSTGRES_MAIN`, `POSTGRES_TEST`
Resolution: CLI args > Environment variables > Profile defaults

Key env vars:
- `MIND_PROVIDER` — LLM provider (openai, claude, gemini, stub)
- `MIND_MODEL` — Model identifier
- `MIND_POSTGRES_DSN` — PostgreSQL connection string
- `MIND_SQLITE_PATH` — SQLite file path
- `MIND_DEV_MODE` — Enable development mode

---

## 5. Phase Gate System

The project uses phase-based development (Phase B through Phase N+).
Each phase has:
- A gate script in `scripts/run_phase_<x>_gate.py`
- Benchmark datasets in `mind/fixtures/`
- Acceptance records in `docs/reports/`

Currently completed: Phases B–M, with Phase N (productization) in progress.

---

## 6. Database Schema

Core tables (managed by Alembic in `alembic/versions/`):
- `objects` — memory objects (all types)
- `embeddings` — vector representations
- `direct_provenance` — lineage tracking
- `governance_audit` — audit records
- `concealed_objects` — concealment records
- `principals`, `sessions`, `namespaces` — user state
- `offline_jobs` — background job queue
- `budget_events` — cost tracking
- `primitive_call_logs` — operation logs
- `feedback_records` — quality signals

SQL table definitions: `mind/kernel/sql_tables.py`
