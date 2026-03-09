"""Optional PostgreSQL integration coverage for Phase B/C gates."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mind.kernel.phase_b import evaluate_phase_b_gate
from mind.kernel.postgres_store import (
    PostgresMemoryStore,
    build_postgres_store_factory,
    run_postgres_migrations,
    temporary_postgres_database,
)
from mind.primitives.phase_c import evaluate_phase_c_gate

POSTGRES_DSN = os.environ.get("MIND_TEST_POSTGRES_DSN")

pytestmark = pytest.mark.skipif(
    POSTGRES_DSN is None,
    reason="set MIND_TEST_POSTGRES_DSN to run PostgreSQL integration tests",
)


def test_postgres_memory_store_round_trip_and_gates() -> None:
    assert POSTGRES_DSN is not None

    with temporary_postgres_database(POSTGRES_DSN, prefix="mind_pytest_b") as database_dsn:
        run_postgres_migrations(database_dsn)
        with PostgresMemoryStore(database_dsn) as store:
            assert store.iter_objects() == []
            assert store.iter_primitive_call_logs() == []
            assert store.iter_budget_events() == []

        store_factory = build_postgres_store_factory(database_dsn)
        phase_b_result = evaluate_phase_b_gate(Path("phase_b.pg"), store_factory=store_factory)

    with temporary_postgres_database(POSTGRES_DSN, prefix="mind_pytest_c") as database_dsn:
        run_postgres_migrations(database_dsn)
        store_factory = build_postgres_store_factory(database_dsn)
        phase_c_result = evaluate_phase_c_gate(Path("phase_c.pg"), store_factory=store_factory)

    assert phase_b_result.phase_b_pass
    assert phase_c_result.phase_c_pass
