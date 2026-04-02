"""Tests for the maintained application layer."""

from __future__ import annotations

from pydantic import ValidationError

from mind.application import (
    ChatCompletionRequest,
    ChatMessage,
    IngestConversationRequest,
    ListMemoriesRequest,
    MindService,
    OwnerSelector,
    SearchMemoriesRequest,
    UpdateMemoryRequest,
)
from mind.config import ConfigManager


def test_owner_selector_requires_exactly_one_identity_mode():
    try:
        OwnerSelector()
        assert False, "OwnerSelector should require exactly one identity mode"
    except ValidationError:
        pass

    try:
        OwnerSelector(
            external_user_id="alice",
            anonymous_session_id="anon-1",
        )
        assert False, "OwnerSelector should reject conflicting identity modes"
    except ValidationError:
        pass


def test_rest_config_resolves_from_config_manager_defaults_and_overrides():
    cfg = ConfigManager.from_dict(
        {
            "rest": {
                "host": "0.0.0.0",
                "port": 9000,
                "cors_allowed_origins": ["http://localhost:3000"],
            }
        }
    ).get()

    assert cfg.rest.host == "0.0.0.0"
    assert cfg.rest.port == 9000
    assert cfg.rest.cors_allowed_origins == ["http://localhost:3000"]


def test_rest_config_defaults_cover_local_frontend_origins():
    cfg = ConfigManager.from_dict({}).get()

    assert cfg.rest.cors_allowed_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_chat_config_resolves_curated_profiles_and_fallback_default():
    curated = ConfigManager.from_dict(
        {
            "llm": {
                "provider": "fake",
                "temperature": 0.1,
                "timeout": 20.0,
                "fake": {
                    "protocols": "fake",
                    "model": "fake-memory-test",
                },
            },
            "chat": {
                "default_profile_id": "fast",
                "profiles": {
                    "fast": {
                        "label": "Fast",
                        "provider": "fake",
                        "model": "fake-fast",
                        "temperature": 0.0,
                    },
                    "careful": {
                        "label": "Careful",
                        "provider": "fake",
                        "model": "fake-careful",
                        "temperature": 0.4,
                        "timeout": 45.0,
                    },
                },
            },
        }
    ).get()

    assert curated.chat.default_profile_id == "fast"
    assert curated.chat.profiles["fast"].label == "Fast"
    assert curated.chat.profiles["fast"].llm.model == "fake-fast"
    assert curated.chat.profiles["careful"].llm.timeout == 45.0

    fallback = ConfigManager.from_dict(
        {
            "llm": {
                "provider": "fake",
                "temperature": 0.3,
                "fake": {
                    "protocols": "fake",
                    "model": "fallback-model",
                },
            }
        }
    ).get()

    assert fallback.chat.default_profile_id == "default"
    assert fallback.chat.profiles["default"].llm.model == "fallback-model"


def test_mind_service_known_owner_crud_flow(memory_config):
    service = MindService(config=memory_config)
    try:
        owner = OwnerSelector(external_user_id="svc-known")
        ingest = service.ingest_conversation(
            IngestConversationRequest(
                owner=owner,
                messages=[ChatMessage(role="user", content="I love black coffee")],
            )
        )
        assert ingest.count == 1
        memory_id = ingest.items[0].id

        search = service.search_memories(
            SearchMemoriesRequest(owner=owner, query="What should I drink?")
        )
        assert search.count == 1
        assert "black coffee" in search.items[0].content.lower()

        listed = service.list_memories(ListMemoriesRequest(owner=owner))
        assert listed.count == 1
        assert listed.items[0].id == memory_id

        fetched = service.get_memory(memory_id)
        assert fetched.id == memory_id

        updated = service.update_memory(
            memory_id,
            UpdateMemoryRequest(content="[self] preference:like=americano"),
        )
        assert updated.canonical_text == "[self] preference:like=americano"

        history = service.get_memory_history(memory_id)
        assert [row.operation.value for row in history.items] == ["ADD", "UPDATE"]

        service.delete_memory(memory_id)

        listed_after_delete = service.list_memories(ListMemoriesRequest(owner=owner))
        assert listed_after_delete.count == 0

        search_after_delete = service.search_memories(
            SearchMemoriesRequest(owner=owner, query="What should I drink?")
        )
        assert search_after_delete.count == 0

        history_after_delete = service.get_memory_history(memory_id)
        assert [row.operation.value for row in history_after_delete.items] == [
            "ADD",
            "UPDATE",
            "DELETE",
        ]
    finally:
        service.close()


def test_mind_service_lists_chat_models_and_completes_chat(memory_config):
    service = MindService(config=memory_config)
    try:
        profiles = service.list_chat_models()
        assert profiles.count == 1
        assert profiles.items[0].id == memory_config.chat.default_profile_id
        assert profiles.items[0].is_default is True

        reply = service.chat_completion(
            ChatCompletionRequest(
                owner=OwnerSelector(external_user_id="svc-chat"),
                model_profile_id=profiles.items[0].id,
                messages=[ChatMessage(role="user", content="Tell me about coffee")],
            )
        )

        assert reply.message.role == "assistant"
        assert "coffee" in reply.message.content.lower()
        assert reply.model_profile_id == profiles.items[0].id
    finally:
        service.close()


def test_mind_service_supports_anonymous_owner(memory_config):
    service = MindService(config=memory_config)
    try:
        owner = OwnerSelector(anonymous_session_id="anon-session-123")
        ingest = service.ingest_conversation(
            IngestConversationRequest(
                owner=owner,
                messages=[ChatMessage(role="user", content="I love green tea")],
            )
        )

        assert ingest.count == 1
        assert ingest.items[0].user_id == "anon-session-123"

        listed = service.list_memories(ListMemoriesRequest(owner=owner))
        assert listed.count == 1
        assert listed.items[0].user_id == "anon-session-123"
    finally:
        service.close()
