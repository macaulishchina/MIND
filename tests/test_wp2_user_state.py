"""WP-2 — user state persistence and provenance projection tests."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import pytest

from mind.app.context import (
    NamespaceContext,
    PrincipalContext,
    PrincipalKind,
    SessionContext,
    SourceChannel,
    project_provenance_from_context,
)
from mind.app.contracts import AppRequest, AppStatus
from mind.app.services.user_state import UserStateService
from mind.kernel.postgres_store import (
    PostgresMemoryStore,
    run_postgres_migrations,
    temporary_postgres_database,
)
from mind.kernel.store import SQLiteMemoryStore
from mind.primitives.contracts import Capability

POSTGRES_DSN = os.environ.get("MIND_TEST_POSTGRES_DSN")


def _make_request(**overrides: Any) -> AppRequest:
    payload: dict[str, Any] = {
        "request_id": f"test-{uuid.uuid4().hex[:8]}",
        "input": {},
    }
    payload.update(overrides)
    return AppRequest(**payload)


def _build_sqlite_store(tmp_path: Path) -> SQLiteMemoryStore:
    return SQLiteMemoryStore(tmp_path / "user_state.sqlite3")


def test_sqlite_principal_crud_roundtrip(tmp_path: Path) -> None:
    store = _build_sqlite_store(tmp_path)

    created = store.insert_principal(
        {
            "principal_id": "principal-1",
            "principal_kind": "user",
            "tenant_id": "acme",
            "user_id": "user-1",
            "roles": ["admin"],
            "capabilities": ["memory_read", "governance_plan"],
            "preferences": {"default_access_mode": "recall"},
        }
    )
    fetched = store.read_principal("principal-1")
    listed = store.list_principals(tenant_id="acme")

    assert created["principal_id"] == "principal-1"
    assert fetched["user_id"] == "user-1"
    assert fetched["roles"] == ["admin"]
    assert fetched["capabilities"] == ["memory_read", "governance_plan"]
    assert fetched["preferences"]["default_access_mode"] == "recall"
    assert [row["principal_id"] for row in listed] == ["principal-1"]


def test_sqlite_session_lifecycle_roundtrip(tmp_path: Path) -> None:
    store = _build_sqlite_store(tmp_path)
    store.insert_principal(
        {
            "principal_id": "principal-2",
            "tenant_id": "acme",
            "roles": [],
            "capabilities": ["memory_read"],
            "preferences": {},
        }
    )

    opened = store.insert_session(
        {
            "session_id": "session-1",
            "principal_id": "principal-2",
            "conversation_id": "conv-1",
            "channel": "rest",
            "client_id": "cli-1",
            "device_id": "dev-1",
            "metadata": {"step": "open"},
        }
    )
    updated = store.update_session(
        "session-1",
        {
            "conversation_id": "conv-2",
            "metadata": {"step": "updated", "stage": "foreground"},
        },
    )
    fetched = store.read_session("session-1")
    listed = store.list_sessions(principal_id="principal-2")

    assert opened["started_at"] == updated["started_at"]
    assert fetched["conversation_id"] == "conv-2"
    assert fetched["metadata"]["step"] == "updated"
    assert fetched["metadata"]["stage"] == "foreground"
    assert [row["session_id"] for row in listed] == ["session-1"]


def test_namespace_isolation_roundtrip(tmp_path: Path) -> None:
    store = _build_sqlite_store(tmp_path)

    store.insert_namespace(
        {
            "namespace_id": "ns-a",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "workspace_id": "workspace-a",
            "visibility_policy": "team",
        }
    )
    store.insert_namespace(
        {
            "namespace_id": "ns-b",
            "tenant_id": "tenant-b",
            "project_id": "project-b",
            "workspace_id": "workspace-b",
            "visibility_policy": "private",
        }
    )

    ns_a = store.read_namespace("ns-a")
    ns_b = store.read_namespace("ns-b")

    assert ns_a["tenant_id"] == "tenant-a"
    assert ns_a["workspace_id"] == "workspace-a"
    assert ns_b["tenant_id"] == "tenant-b"
    assert ns_b["workspace_id"] == "workspace-b"
    assert ns_a["workspace_id"] != ns_b["workspace_id"]


def test_user_state_service_persists_and_resolves_runtime_defaults(tmp_path: Path) -> None:
    store = _build_sqlite_store(tmp_path)
    service = UserStateService(store)

    principal_resp = service.resolve_principal(
        _make_request(
            input={
                "principal_id": "principal-3",
                "tenant_id": "acme",
                "preferences": {
                    "default_access_mode": "reconstruct",
                    "budget_limit": 42.0,
                    "retention_class": "long_term",
                    "dev_mode": True,
                    "conceal_visibility": True,
                    "fallback_policy": "degrade",
                },
            }
        )
    )
    session_resp = service.open_session(
        _make_request(
            input={
                "session_id": "session-3",
                "principal_id": "principal-3",
                "channel": "mcp",
                "conversation_id": "conv-3",
            }
        )
    )
    defaults_resp = service.get_runtime_defaults(
        _make_request(input={"principal_id": "principal-3"})
    )
    fetched_session = service.get_session(_make_request(input={"session_id": "session-3"}))

    assert principal_resp.status == AppStatus.OK
    assert session_resp.status == AppStatus.OK
    assert defaults_resp.status == AppStatus.OK
    assert defaults_resp.result == {
        "default_access_mode": "reconstruct",
        "budget_limit": 42.0,
        "retention_class": "long_term",
        "dev_mode": True,
        "conceal_visibility": True,
        "fallback_policy": "degrade",
    }
    assert fetched_session.status == AppStatus.OK
    assert fetched_session.result is not None
    assert fetched_session.result["channel"] == "mcp"
    assert fetched_session.result["metadata"]["request_id"].startswith("test-")


def test_project_provenance_from_context_maps_only_supported_fields() -> None:
    principal = PrincipalContext(
        principal_id="principal-4",
        principal_kind=PrincipalKind.USER,
        tenant_id="acme",
        user_id="user-4",
        roles=["operator"],
        capabilities=[Capability.MEMORY_READ, Capability.GOVERNANCE_PLAN],
    )
    session = SessionContext(
        session_id="session-4",
        conversation_id="conv-4",
        channel=SourceChannel.REST,
        device_id="device-4",
        request_id="request-4",
    )
    namespace = NamespaceContext(
        namespace_id="ns-4",
        tenant_id="acme",
        project_id="project-4",
        workspace_id="workspace-4",
    )

    provenance = project_provenance_from_context(principal, session, namespace)
    dumped = provenance.model_dump(mode="json")

    assert provenance.producer_kind.value == "user"
    assert provenance.producer_id == "principal-4"
    assert provenance.source_channel.value == "api"
    assert provenance.tenant_id == "acme"
    assert provenance.user_id == "user-4"
    assert provenance.device_id == "device-4"
    assert provenance.session_id == "session-4"
    assert provenance.request_id == "request-4"
    assert provenance.conversation_id == "conv-4"
    assert "roles" not in dumped
    assert "capabilities" not in dumped
    assert "project_id" not in dumped
    assert "workspace_id" not in dumped


@pytest.mark.skipif(
    POSTGRES_DSN is None,
    reason="set MIND_TEST_POSTGRES_DSN to run PostgreSQL user-state tests",
)
def test_postgres_user_state_roundtrip() -> None:
    assert POSTGRES_DSN is not None

    with temporary_postgres_database(POSTGRES_DSN, prefix="mind_user_state") as database_dsn:
        run_postgres_migrations(database_dsn)
        with PostgresMemoryStore(database_dsn) as store:
            principal = store.insert_principal(
                {
                    "principal_id": "principal-pg",
                    "tenant_id": "tenant-pg",
                    "roles": ["owner"],
                    "capabilities": ["memory_read"],
                    "preferences": {"default_access_mode": "flash"},
                }
            )
            session = store.insert_session(
                {
                    "session_id": "session-pg",
                    "principal_id": "principal-pg",
                    "channel": "rest",
                    "metadata": {"source": "pytest"},
                }
            )
            namespace = store.insert_namespace(
                {
                    "namespace_id": "ns-pg",
                    "tenant_id": "tenant-pg",
                    "workspace_id": "workspace-pg",
                    "visibility_policy": "shared",
                }
            )

            assert store.read_principal("principal-pg")["tenant_id"] == "tenant-pg"
            assert store.read_session("session-pg")["metadata"]["source"] == "pytest"
            assert store.read_namespace("ns-pg")["workspace_id"] == "workspace-pg"
            assert [
                row["principal_id"] for row in store.list_principals()
            ] == [principal["principal_id"]]
            assert [row["session_id"] for row in store.list_sessions()] == [session["session_id"]]
            assert namespace["visibility_policy"] == "shared"
