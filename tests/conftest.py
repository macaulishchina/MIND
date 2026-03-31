"""Shared test fixtures."""

import pytest

from mind.config import ConfigManager
from mind.config.manager import _DEFAULT_TEST_TOML
from mind.config.schema import HistoryStoreConfig
from mind.storage import SQLiteManager
from mind.stl.store import SQLiteSTLStore


@pytest.fixture
def history_store(tmp_path):
    """Create a SQLiteManager with a temporary database."""
    config = HistoryStoreConfig(db_path=str(tmp_path / "test_history.db"))
    store = SQLiteManager(config)
    yield store
    store.close()


@pytest.fixture
def stl_store(tmp_path):
    """Create a SQLiteSTLStore with a temporary database."""
    store = SQLiteSTLStore(db_path=str(tmp_path / "test_stl.db"))
    yield store
    store.close()


@pytest.fixture
def memory_config(tmp_path):
    """Create a MemoryConfig for testing.

    Loads mindt.toml (test config) and overrides storage paths for isolation.
    The LLM and embedding backends are selected by the TOML itself.

    The returned config can be passed directly to ``Memory(config=...)``.
    """
    mgr = ConfigManager(toml_path=_DEFAULT_TEST_TOML)
    return mgr.get(overrides={
        "llm": {
            "provider": "fake",
            "batch": False,
        },
        "vector_store": {
            "collection_name": f"test_memories_{tmp_path.name}",
            "url": "",
            "api_key": "",
        },
        "history_store": {"db_path": str(tmp_path / "test_history.db")},
        "stl_store": {"provider": "sqlite", "db_path": str(tmp_path / "test_stl.db")},
        "logging": {"console": False, "file": ""},
    })
