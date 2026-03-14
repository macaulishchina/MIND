# Rules: Database Migrations (`alembic/versions/`)

> Load this file when creating or modifying Alembic migrations.

---

## Location

- Config: `alembic.ini`
- Env: `alembic/env.py`
- Migrations: `alembic/versions/`
- SQL Tables: `mind/kernel/sql_tables.py`

## Naming Convention

Migration files: `YYYYMMDD_NNNN_description.py`

Example: `20260313_0011_add_tags_table.py`

## Rules

1. **Never modify existing migrations**: Once a migration is committed and
   deployed, it is immutable. Create a new migration for changes.

2. **One concern per migration**: Each migration does one thing (add table,
   add column, add index). Keep them small and reviewable.

3. **Reversible**: Always implement both `upgrade()` and `downgrade()`.
   If a downgrade is truly impossible, document why with a comment.

4. **SQL tables file**: Keep `mind/kernel/sql_tables.py` in sync with migrations.
   The file defines the canonical table structure.

5. **Test the migration**: Run `alembic upgrade head` and `alembic downgrade -1`
   locally before committing.

6. **Data migrations**: If you need to migrate data (not just schema), create
   a separate migration with clear comments about what data is being transformed.

7. **Dependencies**: If the migration adds a table/column that the kernel code
   depends on, the kernel code change and migration MUST be in the same commit.

## Current Migration Chain

```
0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010
(initial) (indexes) (pgvector) (jobs) (provenance) (gov audit) (conceal) (user state) (job provider) (feedback)
```

Next migration number: `0011`.
