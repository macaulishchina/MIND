# Rules: Kernel Layer (`mind/kernel/`)

> Load this file when modifying anything under `mind/kernel/`.

---

## Scope

The kernel provides the lowest-level storage abstraction. Everything above
depends on it. Changes here have the **widest blast radius**.

## Key Files

| File | Purpose |
|------|---------|
| `store.py` | `MemoryStore` protocol + `SQLiteMemoryStore` implementation |
| `postgres_store.py` | `PostgresMemoryStore` implementation |
| `schema.py` | Object types, validation, required fields |
| `retrieval.py` | Search and matching algorithms |
| `provenance.py` | Lineage tracking records |
| `governance.py` | Concealment and audit records |
| `graph.py` | Object relationship algorithms |
| `embedding.py` | Dense retrieval support |
| `pg_vector.py` | PostgreSQL vector operations |
| `sql_tables.py` | SQLAlchemy table definitions |
| `priority.py` | Priority scheduling |

## Rules

1. **Protocol first**: Any new store operation MUST be added to the `MemoryStore`
   protocol in `store.py` before implementing it.

2. **Both backends**: Every protocol method MUST be implemented in both
   `SQLiteMemoryStore` and `PostgresMemoryStore`. Missing one = broken tests or broken prod.

3. **Schema validation**: New object types MUST be added to:
   - `CORE_OBJECT_TYPES` set in `schema.py`
   - `REQUIRED_METADATA_FIELDS` dict in `schema.py`
   - `ensure_valid_object()` function must handle them.

4. **Migrations**: Schema changes (new tables, columns) require a new Alembic
   migration in `alembic/versions/`. See `.ai/rules/migration.md`.

5. **No business logic**: The kernel handles storage, retrieval, and validation
   only. Decision-making belongs in primitives or domain services.

6. **Transaction safety**: All multi-object writes MUST use `store.transaction()`.
   Never do partial writes that could leave the store inconsistent.

7. **Test with SQLite**: All kernel tests use `SQLiteMemoryStore` with `tmp_path`.
   PostgreSQL regression tests are separate (`scripts/run_postgres_regression.py`).

## Common Mistakes

- Adding a method to `SQLiteMemoryStore` but forgetting `PostgresMemoryStore`.
- Adding a new object type but not updating `REQUIRED_METADATA_FIELDS`.
- Doing raw SQL outside of the kernel layer.
