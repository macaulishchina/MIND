"""Memory pipeline tests using deterministic local backends."""

from mind.config.models import FactFamily, MemoryStatus, OwnerContext
from mind.memory import Memory


class TestMemoryEndToEnd:
    """Exercise the owner-centered memory pipeline with fake backends."""

    def test_add_and_search_known_owner(self, memory_config):
        m = Memory(memory_config)

        results = m.add(
            messages=[{"role": "user", "content": "I love black coffee"}],
            user_id="alice",
        )

        assert len(results) == 1
        item = results[0]
        assert item.owner_id is not None
        assert item.subject_ref == "self"
        assert item.fact_family == FactFamily.PREFERENCE
        assert "black coffee" in item.content.lower()
        assert item.status == MemoryStatus.ACTIVE

        search_results = m.search(
            query="What drink do you recommend?",
            user_id="alice",
        )
        assert len(search_results) >= 1
        assert any("black coffee" in r.content.lower() for r in search_results)

    def test_single_value_fields_update_with_version_tracking(self, memory_config):
        m = Memory(memory_config)

        first = m.add(
            messages=[{"role": "user", "content": "My name is Dave"}],
            user_id="bob",
        )
        second = m.add(
            messages=[{"role": "user", "content": "My name is David"}],
            user_id="bob",
        )

        all_memories = m.get_all(user_id="bob")
        assert len(all_memories) == 1
        assert all_memories[0].content == "[self] name=David"
        assert second[0].version_of == first[0].id

        old_item = m.get(first[0].id)
        assert old_item is not None
        assert old_item.status == MemoryStatus.DELETED

    def test_single_chunk_keeps_only_final_single_value_memory(self, memory_config):
        m = Memory(memory_config)

        results = m.add(
            messages=[
                {"role": "user", "content": "My name is Dave"},
                {"role": "user", "content": "My name is David"},
            ],
            user_id="bob-chunk",
        )

        all_memories = m.get_all(user_id="bob-chunk")
        assert len(all_memories) == 1
        assert all_memories[0].content == "[self] name=David"
        assert all_memories[0].version_of is None
        assert len(results) == 1

    def test_anonymous_owner_is_reused(self, memory_config):
        m = Memory(memory_config)
        owner = OwnerContext(anonymous_session_id="anon-session-1")

        first = m.add(
            messages=[{"role": "user", "content": "My name is June"}],
            owner=owner,
        )
        second = m.add(
            messages=[{"role": "user", "content": "I live in Hangzhou"}],
            owner=owner,
        )

        assert first[0].owner_id == second[0].owner_id

        search_results = m.search(
            query="Where does the user live?",
            user_id="anon-session-1",
        )
        assert any("hangzhou" in item.content.lower() for item in search_results)

    def test_third_party_named_subject_creates_relation_and_attribute(self, memory_config):
        m = Memory(memory_config)

        results = m.add(
            messages=[{"role": "user", "content": "My friend Green is a football player"}],
            user_id="mike",
        )

        assert len(results) == 2
        assert {item.subject_ref for item in results} == {"friend:green"}
        contents = {item.content for item in results}
        assert "[friend:green] relation_to_owner=friend" in contents
        assert "[friend:green] occupation=football player" in contents

    def test_third_party_unknown_subject_reuses_placeholder_within_one_fact(self, memory_config):
        m = Memory(memory_config)

        results = m.add(
            messages=[{"role": "user", "content": "I have a friend who is gay"}],
            user_id="mike",
        )

        assert len(results) == 2
        subject_refs = {item.subject_ref for item in results}
        assert len(subject_refs) == 1
        only_ref = next(iter(subject_refs))
        assert only_ref.startswith("friend:unknown_")

    def test_manual_update_keeps_history(self, memory_config):
        m = Memory(memory_config)
        results = m.add(
            messages=[{"role": "user", "content": "I work at Stripe"}],
            user_id="eve",
        )

        updated = m.update(results[0].id, "[self] workplace=OpenAI")
        assert updated is not None
        assert updated.canonical_text == "[self] workplace=OpenAI"

        hist = m.history(results[0].id)
        operations = [h["operation"] for h in hist]
        assert "ADD" in operations
        assert "UPDATE" in operations

    def test_stl_extraction_uses_global_extraction_temperature(self, memory_config):
        memory_config.llm.extraction_temperature = 0.42
        memory_config.llm_stages = {}
        m = Memory(memory_config)
        captured = {}

        def capture_generate(messages, temperature=None):
            captured["temperature"] = temperature
            return ""

        m.stl_extraction_llm.generate = capture_generate

        m._extract_stl("User: My name is Alice")

        assert captured["temperature"] == 0.42

    def test_mvp_public_api_smoke_path(self, memory_config):
        """Exercise the maintained MVP public API surface in one flow."""
        m = Memory(memory_config)

        added = m.add(
            messages=[{"role": "user", "content": "I love black coffee"}],
            user_id="mvp-user",
        )
        assert len(added) == 1
        memory_id = added[0].id

        search_results = m.search("What should I drink?", user_id="mvp-user")
        assert any("black coffee" in item.content.lower() for item in search_results)

        fetched = m.get(memory_id)
        assert fetched is not None
        assert fetched.content == added[0].content

        all_memories = m.get_all("mvp-user")
        assert [item.id for item in all_memories] == [memory_id]

        updated = m.update(memory_id, "[self] preference:like=americano")
        assert updated is not None
        assert updated.canonical_text == "[self] preference:like=americano"

        history_after_update = m.history(memory_id)
        assert [row["operation"] for row in history_after_update] == [
            "ADD",
            "UPDATE",
        ]

        assert m.delete(memory_id) is True

        deleted = m.get(memory_id)
        assert deleted is not None
        assert deleted.status == MemoryStatus.DELETED

        assert m.get_all("mvp-user") == []
        assert m.search("What should I drink?", user_id="mvp-user") == []

        history_after_delete = m.history(memory_id)
        assert [row["operation"] for row in history_after_delete] == [
            "ADD",
            "UPDATE",
            "DELETE",
        ]
