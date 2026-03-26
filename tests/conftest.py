"""Shared test fixtures."""

import pytest

from mind.config import ConfigManager
from mind.config.schema import HistoryStoreConfig
from mind.storage import SQLiteManager


@pytest.fixture
def history_store(tmp_path):
    """Create a SQLiteManager with a temporary database."""
    config = HistoryStoreConfig(db_path=str(tmp_path / "test_history.db"))
    store = SQLiteManager(config)
    yield store
    store.close()


@pytest.fixture
def memory_config(tmp_path):
    """Create a MemoryConfig for testing.

    Loads mind.toml defaults, then overrides storage paths for isolation.
    API credentials come from mind.toml — fill them there before running.
    """
    mgr = ConfigManager()
    return mgr.get(overrides={
        "vector_store": {"collection_name": "test_memories"},
        "history_store": {"db_path": str(tmp_path / "test_history.db")},
    })