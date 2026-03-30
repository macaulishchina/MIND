"""Tests for history store backend selection."""

import pytest

from mind.config.schema import HistoryStoreConfig
from mind.storage import HistoryStoreFactory, PostgresHistoryManager, SQLiteManager


class TestHistoryStoreFactory:
    """Validate history store provider wiring."""

    def test_create_sqlite_history_store(self, tmp_path):
        store = HistoryStoreFactory.create(
            HistoryStoreConfig(
                provider="sqlite",
                db_path=str(tmp_path / "test_history.db"),
            )
        )
        try:
            assert isinstance(store, SQLiteManager)
        finally:
            store.close()

    def test_create_postgres_history_store_requires_dsn(self):
        with pytest.raises(ValueError):
            HistoryStoreFactory.create(
                HistoryStoreConfig(provider="postgres", dsn="")
            )

    def test_invalid_provider_raises(self):
        with pytest.raises(ValueError):
            HistoryStoreFactory.create(
                HistoryStoreConfig(provider="unsupported")
            )

    def test_postgres_factory_path_can_be_monkeypatched(self, monkeypatch):
        created = []

        def fake_ensure_table(self):
            created.append(self.table_name)

        monkeypatch.setattr(PostgresHistoryManager, "_ensure_table", fake_ensure_table)

        store = HistoryStoreFactory.create(
            HistoryStoreConfig(
                provider="postgres",
                dsn="postgresql://example/mind",
                table_name="memory_history",
            )
        )

        assert isinstance(store, PostgresHistoryManager)
        assert created == ["memory_history"]
