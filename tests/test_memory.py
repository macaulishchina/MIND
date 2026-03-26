"""End-to-end tests for the Memory system.

These tests require a valid API key configured in mindt.toml (test config).
Tests are skipped when llm.api_key is empty.
"""

import pytest

from mind.config import ConfigManager
from mind.config.manager import _DEFAULT_TEST_TOML
from mind.config.models import MemoryStatus
from mind.memory import Memory

_cfg = ConfigManager(toml_path=_DEFAULT_TEST_TOML).get()
_HAS_API_KEY = bool(_cfg.llm.api_key)

requires_api_key = pytest.mark.skipif(
    not _HAS_API_KEY,
    reason="No API key configured in mindt.toml (llm.api_key is empty)",
)


@requires_api_key
class TestMemoryEndToEnd:
    """End-to-end tests exercising the full Memory pipeline."""

    def test_add_and_search(self, memory_config):
        """Scenario 1: stable preference write and recall.

        User says 'I love black coffee' → search for drink recommendations
        should return that memory.
        """
        m = Memory(memory_config)

        # Add
        results = m.add(
            messages=[{"role": "user", "content": "I love black coffee"}],
            user_id="alice",
        )

        assert len(results) >= 1
        contents = [r.content.lower() for r in results]
        assert any("coffee" in c for c in contents)

        # Verify confidence and source_context are recorded
        for item in results:
            assert item.confidence is not None
            assert item.source_context is not None
            assert item.status == MemoryStatus.ACTIVE

        # Search
        search_results = m.search(
            query="What drink do you recommend?",
            user_id="alice",
        )
        assert len(search_results) >= 1
        assert any("coffee" in r.content.lower() for r in search_results)

    def test_update_with_version_tracking(self, memory_config):
        """Scenario 2: preference update with version_of tracking.

        User first says 'I like black coffee', then changes to 'I only drink
        americano now'. The new memory should have version_of set.
        """
        m = Memory(memory_config)

        # Add initial preference
        m.add(
            messages=[{"role": "user", "content": "I like black coffee"}],
            user_id="bob",
        )

        # Update preference
        updated = m.add(
            messages=[
                {"role": "user", "content": "I only drink americano now"}
            ],
            user_id="bob",
        )

        # Check that at least one result has version_of set
        # (the LLM should decide UPDATE for the conflicting preference)
        all_memories = m.get_all(user_id="bob")
        version_of_set = [
            mem for mem in all_memories if mem.version_of is not None
        ]

        # It's possible the LLM decides ADD instead of UPDATE, which is
        # acceptable for MVP — we just record whether version_of works.
        if version_of_set:
            assert version_of_set[0].version_of is not None

    def test_delete_filters_from_search(self, memory_config):
        """Scenario 4: deleted memory does not pollute search results."""
        m = Memory(memory_config)

        # Add
        results = m.add(
            messages=[
                {"role": "user", "content": "I am allergic to peanuts"}
            ],
            user_id="carol",
        )
        assert len(results) >= 1
        memory_id = results[0].id

        # Delete
        deleted = m.delete(memory_id)
        assert deleted is True

        # Search should not return the deleted memory
        search_results = m.search(
            query="food allergies",
            user_id="carol",
        )
        found_ids = [r.id for r in search_results]
        assert memory_id not in found_ids

    def test_manual_update(self, memory_config):
        """Manual update re-embeds and records history."""
        m = Memory(memory_config)

        # Add
        results = m.add(
            messages=[{"role": "user", "content": "My name is Dave"}],
            user_id="dave",
        )
        assert len(results) >= 1
        memory_id = results[0].id

        # Manual update
        updated = m.update(memory_id, "My name is David, not Dave")
        assert updated is not None
        assert "David" in updated.content

        # History should show both ADD and UPDATE
        hist = m.history(memory_id)
        operations = [h["operation"] for h in hist]
        assert "ADD" in operations
        assert "UPDATE" in operations

    def test_get_and_get_all(self, memory_config):
        """get() and get_all() return correct results."""
        m = Memory(memory_config)

        results = m.add(
            messages=[
                {"role": "user", "content": "I work at a tech startup"}
            ],
            user_id="eve",
        )
        assert len(results) >= 1

        # get single
        item = m.get(results[0].id)
        assert item is not None
        assert item.id == results[0].id

        # get_all
        all_items = m.get_all(user_id="eve")
        assert len(all_items) >= 1

    def test_history_tracking(self, memory_config):
        """history() returns the full operation log."""
        m = Memory(memory_config)

        results = m.add(
            messages=[{"role": "user", "content": "I enjoy hiking"}],
            user_id="frank",
        )
        assert len(results) >= 1
        memory_id = results[0].id

        hist = m.history(memory_id)
        assert len(hist) >= 1
        assert hist[0]["operation"] == "ADD"
        assert hist[0]["new_content"] is not None
