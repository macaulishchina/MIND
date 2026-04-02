"""Tests for the maintained REST adapter."""

from __future__ import annotations

from fastapi.testclient import TestClient

from mind.interfaces.rest import create_app


def test_rest_api_crud_flow(memory_config):
    app = create_app(config=memory_config)

    with TestClient(app) as client:
        capabilities = client.get("/api/v1/capabilities")
        assert capabilities.status_code == 200
        assert capabilities.json()["adapters"]["rest"] is True
        assert "chat_completion" in capabilities.json()["operations"]

        chat_models = client.get("/api/v1/chat/models")
        assert chat_models.status_code == 200
        assert chat_models.json()["count"] == 1
        profile_id = chat_models.json()["items"][0]["id"]

        chat = client.post(
            "/api/v1/chat/completions",
            json={
                "owner": {"external_user_id": "api-known"},
                "model_profile_id": profile_id,
                "messages": [{"role": "user", "content": "Coffee tips?"}],
            },
        )
        assert chat.status_code == 200
        assert chat.json()["message"]["role"] == "assistant"
        assert "coffee" in chat.json()["message"]["content"].lower()

        ingest = client.post(
            "/api/v1/ingestions",
            json={
                "owner": {"external_user_id": "api-known"},
                "messages": [{"role": "user", "content": "I love black coffee"}],
            },
        )
        assert ingest.status_code == 200
        payload = ingest.json()
        assert payload["count"] == 1
        memory_id = payload["items"][0]["id"]

        search = client.post(
            "/api/v1/memories/search",
            json={
                "owner": {"external_user_id": "api-known"},
                "query": "What should I drink?",
            },
        )
        assert search.status_code == 200
        assert search.json()["count"] == 1

        listed = client.get("/api/v1/memories", params={"external_user_id": "api-known"})
        assert listed.status_code == 200
        assert listed.json()["count"] == 1

        fetched = client.get(f"/api/v1/memories/{memory_id}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == memory_id

        updated = client.patch(
            f"/api/v1/memories/{memory_id}",
            json={"content": "[self] preference:like=americano"},
        )
        assert updated.status_code == 200
        assert updated.json()["canonical_text"] == "[self] preference:like=americano"

        history = client.get(f"/api/v1/memories/{memory_id}/history")
        assert history.status_code == 200
        assert [row["operation"] for row in history.json()["items"]] == ["ADD", "UPDATE"]

        deleted = client.delete(f"/api/v1/memories/{memory_id}")
        assert deleted.status_code == 204

        listed_after_delete = client.get(
            "/api/v1/memories",
            params={"external_user_id": "api-known"},
        )
        assert listed_after_delete.status_code == 200
        assert listed_after_delete.json()["count"] == 0

        search_after_delete = client.post(
            "/api/v1/memories/search",
            json={
                "owner": {"external_user_id": "api-known"},
                "query": "What should I drink?",
            },
        )
        assert search_after_delete.status_code == 200
        assert search_after_delete.json()["count"] == 0

        history_after_delete = client.get(f"/api/v1/memories/{memory_id}/history")
        assert history_after_delete.status_code == 200
        assert [row["operation"] for row in history_after_delete.json()["items"]] == [
            "ADD",
            "UPDATE",
            "DELETE",
        ]


def test_rest_api_supports_anonymous_owner(memory_config):
    app = create_app(config=memory_config)

    with TestClient(app) as client:
        ingest = client.post(
            "/api/v1/ingestions",
            json={
                "owner": {"anonymous_session_id": "anon-rest-1"},
                "messages": [{"role": "user", "content": "I love green tea"}],
            },
        )
        assert ingest.status_code == 200
        assert ingest.json()["items"][0]["user_id"] == "anon-rest-1"

        listed = client.get(
            "/api/v1/memories",
            params={"anonymous_session_id": "anon-rest-1"},
        )
        assert listed.status_code == 200
        assert listed.json()["count"] == 1


def test_rest_api_rejects_invalid_owner_selector(memory_config):
    app = create_app(config=memory_config)

    with TestClient(app) as client:
        bad_ingest = client.post(
            "/api/v1/ingestions",
            json={
                "owner": {
                    "external_user_id": "alice",
                    "anonymous_session_id": "anon-1",
                },
                "messages": [{"role": "user", "content": "I love tea"}],
            },
        )
        assert bad_ingest.status_code == 400

        bad_list = client.get(
            "/api/v1/memories",
            params={
                "external_user_id": "alice",
                "anonymous_session_id": "anon-1",
            },
        )
        assert bad_list.status_code == 400


def test_rest_api_returns_404_for_missing_memory(memory_config):
    app = create_app(config=memory_config)

    with TestClient(app) as client:
        missing_get = client.get("/api/v1/memories/missing")
        assert missing_get.status_code == 404

        missing_update = client.patch(
            "/api/v1/memories/missing",
            json={"content": "[self] preference:like=tea"},
        )
        assert missing_update.status_code == 404

        missing_delete = client.delete("/api/v1/memories/missing")
        assert missing_delete.status_code == 404

        missing_history = client.get("/api/v1/memories/missing/history")
        assert missing_history.status_code == 404


def test_rest_api_rejects_unknown_chat_model_profile(memory_config):
    app = create_app(config=memory_config)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat/completions",
            json={
                "owner": {"external_user_id": "api-known"},
                "model_profile_id": "missing-profile",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )

        assert response.status_code == 400
