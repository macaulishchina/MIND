"""Tests for SQLite relational storage."""

from mind.config.models import MemoryOperation, OwnerContext, OwnerType


class TestSQLiteManager:
    """Tests for the SQLiteManager history tracking."""

    def test_add_and_retrieve_record(self, history_store):
        """A single record can be added and retrieved."""
        record = history_store.add_record(
            memory_id="mem_001",
            user_id="alice",
            operation=MemoryOperation.ADD,
            new_content="User likes black coffee",
        )

        assert record.memory_id == "mem_001"
        assert record.user_id == "alice"
        assert record.operation == MemoryOperation.ADD
        assert record.new_content == "User likes black coffee"
        assert record.old_content is None

        # Retrieve
        history = history_store.get_history("mem_001")
        assert len(history) == 1
        assert history[0].id == record.id

    def test_multiple_records_ordered_by_time(self, history_store):
        """Multiple records for the same memory are ordered by timestamp."""
        history_store.add_record(
            memory_id="mem_002",
            user_id="alice",
            operation=MemoryOperation.ADD,
            new_content="User likes running",
        )
        history_store.add_record(
            memory_id="mem_002",
            user_id="alice",
            operation=MemoryOperation.UPDATE,
            old_content="User likes running",
            new_content="User used to like running but stopped due to knee issues",
        )
        history_store.add_record(
            memory_id="mem_002",
            user_id="alice",
            operation=MemoryOperation.DELETE,
            old_content="User used to like running but stopped due to knee issues",
        )

        history = history_store.get_history("mem_002")
        assert len(history) == 3
        assert history[0].operation == MemoryOperation.ADD
        assert history[1].operation == MemoryOperation.UPDATE
        assert history[2].operation == MemoryOperation.DELETE

    def test_empty_history(self, history_store):
        """Querying history for a non-existent memory returns an empty list."""
        history = history_store.get_history("nonexistent")
        assert history == []

    def test_metadata_preserved(self, history_store):
        """Metadata is stored and retrieved correctly."""
        history_store.add_record(
            memory_id="mem_003",
            user_id="alice",
            operation=MemoryOperation.ADD,
            new_content="Test",
            metadata={"version_of": "mem_001", "source": "test"},
        )

        history = history_store.get_history("mem_003")
        assert len(history) == 1
        assert history[0].metadata["version_of"] == "mem_001"
        assert history[0].metadata["source"] == "test"

    def test_resolve_known_owner_reuses_same_record(self, history_store):
        first = history_store.resolve_owner(
            OwnerContext(external_user_id="alice", display_name="Alice")
        )
        second = history_store.resolve_owner(
            OwnerContext(external_user_id="alice", channel="web")
        )

        assert first.owner_id == second.owner_id
        assert second.owner_type == OwnerType.KNOWN
        assert second.display_name == "Alice"
        assert second.channel == "web"

    def test_named_subject_is_owner_local_and_stable(self, history_store):
        owner = history_store.resolve_owner(OwnerContext(external_user_id="mike"))

        first = history_store.get_or_create_named_subject(
            owner_id=owner.owner_id,
            relation_type="friend",
            display_name="Green",
            normalized_name="green",
        )
        second = history_store.get_or_create_named_subject(
            owner_id=owner.owner_id,
            relation_type="friend",
            display_name="Green",
            normalized_name="green",
        )

        assert first.subject_ref == "friend:green"
        assert first.subject_ref == second.subject_ref

    def test_placeholder_subjects_increment_per_relation(self, history_store):
        owner = history_store.resolve_owner(OwnerContext(external_user_id="mike"))

        first = history_store.create_placeholder_subject(
            owner_id=owner.owner_id,
            relation_type="friend",
        )
        second = history_store.create_placeholder_subject(
            owner_id=owner.owner_id,
            relation_type="friend",
        )

        assert first.subject_ref == "friend:unknown_1"
        assert second.subject_ref == "friend:unknown_2"
