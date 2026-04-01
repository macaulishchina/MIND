# Spec Delta: STL Evidence Provenance

> **STATUS: SUPERSEDED** by `stl-v2-grammar` spec.
>
> STL v2 removed all EV lines — evidence is system-side only.
> The `evidence` table DDL has been removed from store.py.
> See `.ai/specs/stl-v2-grammar/spec.md` for the current grammar.

---

_Original v1 content below preserved for historical reference._

---

## MODIFIED Requirements (v1 — no longer active)

### Requirement: ev-syntax

The system SHALL accept `ev()` with the following syntax:

```
ev($id, conf=N, span="…")
```

`conf` is required. `span` is optional. `src` is removed.

#### Scenario: LLM output without src

- WHEN the LLM produces STL output
- THEN `ev()` contains `conf` and optionally `span`, but never `src`

#### Scenario: parser encounters legacy src

- WHEN the parser encounters `ev()` with a `src` parameter
- THEN `src` is silently ignored (backward compatibility)

### Requirement: evidence-batch-provenance

The system SHALL associate each evidence row with its `batch_id`.

#### Scenario: evidence written during store_program

- WHEN `store_program()` inserts evidence rows
- THEN each evidence row includes the program's `batch_id`

#### Scenario: provenance query by batch

- WHEN a caller queries evidence by `batch_id`
- THEN all evidence rows produced by that extraction batch are returned

### Requirement: evidence-table-schema

The `evidence` table SHALL contain:
- `id` (primary key)
- `target_id` (reference to statement)
- `conf` (confidence score)
- `span` (source text fragment, nullable)
- `batch_id` (reference to extraction_batches, nullable for legacy data)
- `residual` (catch-all text, nullable)
- `created_at` (timestamp)

The `src` column SHALL NOT be present in new table DDL.

## REMOVED Requirements

### Requirement: ev-src-parameter

The `src` parameter in `ev()` is removed. Evidence provenance is no longer
expressed in the LLM output; it is derived from the system-assigned `batch_id`.
