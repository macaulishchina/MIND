"""Shared test fixtures."""

import pytest

from mind.config import ConfigManager
from mind.config.manager import _DEFAULT_TEST_TOML
from mind.config.schema import HistoryStoreConfig
from mind.storage import SQLiteManager
from mind.stl.store import SQLiteSTLStore


def _merge_nested_dict(base: dict, overrides: dict) -> dict:
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_nested_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def build_fake_memory_config(tmp_path, overrides: dict | None = None):
    """Build an isolated MemoryConfig that explicitly uses fake backends.

    Tests should use this helper or the ``memory_config`` fixture when they do
    not need live model behavior. This avoids accidental token spend even if the
    default TOML provider changes later.
    """
    mgr = ConfigManager(toml_path=_DEFAULT_TEST_TOML)
    fake_stage = {
        "provider": "fake",
        "model": "fake-memory-test",
        "temperature": 0.0,
        "batch": False,
    }
    base_overrides = {
        "llm": {
            "provider": "fake",
            "batch": False,
            "decision": dict(fake_stage),
            "stl_extraction": dict(fake_stage),
        },
        "vector_store": {
            "collection_name": f"test_memories_{tmp_path.name}",
            "url": "",
            "api_key": "",
        },
        "history_store": {"db_path": str(tmp_path / "test_history.db")},
        "stl_store": {"provider": "sqlite", "db_path": str(tmp_path / "test_stl.db")},
        "logging": {"console": False, "file": ""},
    }
    return mgr.get(overrides=_merge_nested_dict(base_overrides, overrides or {}))


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

    Loads mindt.toml and explicitly overrides the LLM provider to ``fake`` plus
    isolated local stores, so test behavior does not depend on the TOML default
    provider staying fake forever.

    The returned config can be passed directly to ``Memory(config=...)``.
    """
    return build_fake_memory_config(tmp_path)
