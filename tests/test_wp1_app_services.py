"""WP-1 — Application Service Layer verification tests."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError as PydanticValidationError

from mind.app.context import (
    ExecutionPolicy,
    PrincipalContext,
    SessionContext,
    resolve_execution_context,
)
from mind.app.contracts import AppErrorCode, AppRequest, AppResponse, AppStatus
from mind.app.errors import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
    map_domain_error,
)
from mind.kernel.store import SQLiteMemoryStore, StoreError

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_request(**overrides: Any) -> AppRequest:
    defaults: dict[str, Any] = {
        "request_id": f"test-{uuid.uuid4().hex[:8]}",
        "input": {},
    }
    defaults.update(overrides)
    return AppRequest(**defaults)


def _build_sqlite_store(tmp_path: Path) -> SQLiteMemoryStore:
    db = tmp_path / "test.sqlite3"
    return SQLiteMemoryStore(str(db))


# ---------------------------------------------------------------------------
# 1. Contract models
# ---------------------------------------------------------------------------

class TestContracts:
    """AppRequest, AppResponse, AppError serialization."""

    def test_app_request_has_request_id(self) -> None:
        req = _make_request()
        assert req.request_id.startswith("test-")

    def test_app_response_default_ok(self) -> None:
        resp = AppResponse()
        assert resp.status == AppStatus.OK
        assert resp.error is None

    def test_app_response_with_error(self) -> None:
        from mind.app.contracts import AppError

        err = AppError(code=AppErrorCode.NOT_FOUND, message="missing")
        resp = AppResponse(status=AppStatus.NOT_FOUND, error=err)
        assert resp.status == AppStatus.NOT_FOUND
        assert resp.error is not None
        assert resp.error.code == AppErrorCode.NOT_FOUND


# ---------------------------------------------------------------------------
# 2. Context and execution context resolution
# ---------------------------------------------------------------------------

class TestContext:
    """PrincipalContext, SessionContext, ExecutionPolicy, and projection."""

    def test_resolve_execution_context_defaults(self) -> None:
        ctx = resolve_execution_context()
        assert ctx.actor == "system"
        assert ctx.budget_scope_id == "global"

    def test_resolve_execution_context_with_principal(self) -> None:
        principal = PrincipalContext(principal_id="user-42", tenant_id="acme")
        ctx = resolve_execution_context(principal=principal)
        assert ctx.actor == "user-42"

    def test_resolve_with_session_sets_budget_scope(self) -> None:
        session = SessionContext(session_id="sess-abc")
        ctx = resolve_execution_context(session=session)
        assert ctx.budget_scope_id == "sess-abc"

    def test_resolve_with_policy_sets_budget_limit(self) -> None:
        policy = ExecutionPolicy(budget_limit=50.0)
        ctx = resolve_execution_context(policy=policy)
        assert ctx.budget_limit == 50.0

    def test_principal_context_frozen(self) -> None:
        p = PrincipalContext(principal_id="test")
        with pytest.raises(PydanticValidationError):
            p.principal_id = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3. Error mapping
# ---------------------------------------------------------------------------

class TestErrorMapping:
    """map_domain_error covers domain error → AppError."""

    def test_store_error(self) -> None:
        err = map_domain_error(StoreError("db fail"))
        assert err.code == AppErrorCode.STORE_ERROR

    def test_app_service_error(self) -> None:
        err = map_domain_error(NotFoundError("gone"))
        assert err.code == AppErrorCode.NOT_FOUND

    def test_authorization_error(self) -> None:
        err = map_domain_error(AuthorizationError("denied"))
        assert err.code == AppErrorCode.AUTHORIZATION_ERROR

    def test_validation_error(self) -> None:
        err = map_domain_error(ValidationError("bad input"))
        assert err.code == AppErrorCode.VALIDATION_ERROR

    def test_generic_exception_fallback(self) -> None:
        err = map_domain_error(RuntimeError("unknown"))
        assert err.code == AppErrorCode.INTERNAL_ERROR

    def test_governance_error(self) -> None:
        from mind.governance.service import GovernanceServiceError

        err = map_domain_error(GovernanceServiceError("gov fail"))
        assert err.code == AppErrorCode.GOVERNANCE_EXECUTION_FAILED

    def test_access_error(self) -> None:
        from mind.access.service import AccessServiceError

        err = map_domain_error(AccessServiceError("access fail"))
        assert err.code == AppErrorCode.ACCESS_SERVICE_ERROR

    def test_offline_error(self) -> None:
        from mind.offline.service import OfflineMaintenanceError

        err = map_domain_error(OfflineMaintenanceError("offline fail"))
        assert err.code == AppErrorCode.OFFLINE_MAINTENANCE_ERROR


# ---------------------------------------------------------------------------
# 4. Registry builds successfully
# ---------------------------------------------------------------------------

class TestRegistry:
    """AppServiceRegistry builds for SQLite."""

    def test_build_registry_sqlite(self, tmp_path: Path) -> None:
        from mind.app.registry import build_app_registry
        from mind.cli_config import resolve_cli_config

        config = resolve_cli_config(
            backend="sqlite",
            sqlite_path=str(tmp_path / "reg_test.sqlite3"),
        )
        with build_app_registry(config) as registry:
            assert registry.store is not None
            assert registry.primitive_service is not None
            assert registry.access_service is not None
            assert registry.governance_service is not None
            assert registry.offline_service is not None
            assert registry.memory_ingest_service is not None
            assert registry.memory_query_service is not None
            assert registry.memory_access_service is not None
            assert registry.governance_app_service is not None
            assert registry.offline_job_app_service is not None
            assert registry.user_state_service is not None
            assert registry.system_status_service is not None


# ---------------------------------------------------------------------------
# 5. Service roundtrips
# ---------------------------------------------------------------------------

class TestIngestService:
    """MemoryIngestService.remember() roundtrip."""

    def test_remember_success(self, tmp_path: Path) -> None:
        from mind.app.services.ingest import MemoryIngestService
        from mind.primitives.service import PrimitiveService

        store = _build_sqlite_store(tmp_path)
        svc = MemoryIngestService(PrimitiveService(store))

        req = _make_request(input={
            "content": "test memory",
            "episode_id": "ep-test-1",
            "timestamp_order": 1,
        }, idempotency_key="idem-remember-1")
        resp = svc.remember(req)
        assert resp.status == AppStatus.OK
        assert resp.result is not None
        assert "object_id" in resp.result
        assert resp.request_id == req.request_id
        assert resp.idempotency_key == req.idempotency_key

    def test_remember_sets_trace_ref(self, tmp_path: Path) -> None:
        from mind.app.services.ingest import MemoryIngestService
        from mind.primitives.service import PrimitiveService

        store = _build_sqlite_store(tmp_path)
        svc = MemoryIngestService(PrimitiveService(store))

        req = _make_request(input={
            "content": "trace test",
            "episode_id": "ep-trace-1",
            "timestamp_order": 1,
        })
        resp = svc.remember(req)
        assert resp.trace_ref is not None


class TestQueryService:
    """MemoryQueryService roundtrips."""

    def _seed_store(self, store: SQLiteMemoryStore) -> str:
        from mind.primitives.contracts import PrimitiveExecutionContext
        from mind.primitives.service import PrimitiveService

        svc = PrimitiveService(store)
        ctx = PrimitiveExecutionContext(actor="test")
        result = svc.write_raw(
            {
                "record_kind": "user_message",
                "content": "hello world",
                "episode_id": "ep-q-1",
                "timestamp_order": 1,
            },
            ctx,
        )
        return str(result.response["object_id"])  # type: ignore[index]

    def test_get_memory(self, tmp_path: Path) -> None:
        from mind.app.services.query import MemoryQueryService
        from mind.primitives.service import PrimitiveService

        store = _build_sqlite_store(tmp_path)
        oid = self._seed_store(store)

        svc = MemoryQueryService(
            primitive_service=PrimitiveService(store),
            store=store,
        )
        req = _make_request(input={"object_id": oid})
        resp = svc.get_memory(req)
        assert resp.status == AppStatus.OK
        assert resp.result is not None
        assert resp.trace_ref is not None

    def test_list_memories(self, tmp_path: Path) -> None:
        from mind.app.services.query import MemoryQueryService
        from mind.primitives.service import PrimitiveService

        store = _build_sqlite_store(tmp_path)
        self._seed_store(store)

        svc = MemoryQueryService(PrimitiveService(store), store)
        req = _make_request(input={"limit": 10})
        resp = svc.list_memories(req)
        assert resp.status == AppStatus.OK
        assert resp.result is not None
        assert "total" in resp.result


class TestAccessServiceApp:
    """MemoryAccessService roundtrip."""

    def test_ask_returns_response(self, tmp_path: Path) -> None:
        from mind.access.service import AccessService
        from mind.app.services.access import MemoryAccessService
        from mind.primitives.contracts import PrimitiveExecutionContext
        from mind.primitives.service import PrimitiveService

        store = _build_sqlite_store(tmp_path)
        # Seed a memory
        ps = PrimitiveService(store)
        ps.write_raw(
            {
                "record_kind": "user_message",
                "content": "hello",
                "episode_id": "ep-a-1",
                "timestamp_order": 1,
            },
            PrimitiveExecutionContext(actor="test"),
        )

        svc = MemoryAccessService(AccessService(store))
        req = _make_request(input={"query": "hello", "task_id": "t-1", "episode_id": "ep-a-1"})
        resp = svc.ask(req)
        assert resp.status == AppStatus.OK
        assert resp.trace_ref is not None


class TestGovernanceServiceApp:
    """GovernanceAppService plan_conceal roundtrip."""

    def test_plan_conceal(self, tmp_path: Path) -> None:
        from mind.app.services.governance import GovernanceAppService
        from mind.governance.service import GovernanceService
        from mind.primitives.contracts import Capability, PrimitiveExecutionContext
        from mind.primitives.service import PrimitiveService

        store = _build_sqlite_store(tmp_path)
        ps = PrimitiveService(store)
        ctx = PrimitiveExecutionContext(actor="test")
        ps.write_raw(
            {
                "record_kind": "user_message",
                "content": "secret",
                "episode_id": "ep-g-1",
                "timestamp_order": 1,
            },
            ctx,
        )

        svc = GovernanceAppService(GovernanceService(store))
        principal = PrincipalContext(
            principal_id="gov-actor",
            capabilities=[Capability.MEMORY_READ, Capability.GOVERNANCE_PLAN],
        )
        req = _make_request(
            principal=principal,
            input={"episode_id": "ep-g-1", "reason": "test conceal"},
        )
        resp = svc.plan_conceal(req)
        assert resp.status == AppStatus.OK
        assert resp.audit_ref is not None


class TestUserStateService:
    """UserStateService in-memory roundtrip."""

    def test_resolve_and_get_principal(self) -> None:
        from mind.app.services.user_state import UserStateService

        svc = UserStateService()
        req = _make_request(input={"principal_id": "uid-1", "tenant_id": "acme"})
        resp = svc.resolve_principal(req)
        assert resp.status == AppStatus.OK
        assert resp.result is not None
        assert resp.result["principal_id"] == "uid-1"

    def test_open_and_get_session(self) -> None:
        from mind.app.services.user_state import UserStateService

        svc = UserStateService()
        req = _make_request(input={"session_id": "s-1", "principal_id": "uid-1"})
        resp = svc.open_session(req)
        assert resp.status == AppStatus.OK

        get_req = _make_request(input={"session_id": "s-1"})
        get_resp = svc.get_session(get_req)
        assert get_resp.status == AppStatus.OK

    def test_get_runtime_defaults(self) -> None:
        from mind.app.services.user_state import UserStateService

        svc = UserStateService()
        resp = svc.get_runtime_defaults(_make_request())
        assert resp.status == AppStatus.OK
        assert resp.result is not None
        assert "default_access_mode" in resp.result


class TestSystemService:
    """SystemStatusService roundtrips."""

    def test_health_check(self, tmp_path: Path) -> None:
        from mind.app.services.system import SystemStatusService

        store = _build_sqlite_store(tmp_path)
        svc = SystemStatusService(store)
        resp = svc.health()
        assert resp.status == AppStatus.OK
        assert resp.result is not None
        assert resp.result["status"] == "healthy"

    def test_readiness_check(self, tmp_path: Path) -> None:
        from mind.app.services.system import SystemStatusService

        store = _build_sqlite_store(tmp_path)
        svc = SystemStatusService(store)
        resp = svc.readiness()
        assert resp.status == AppStatus.OK

    def test_config_summary(self, tmp_path: Path) -> None:
        from mind.app.services.system import SystemStatusService

        store = _build_sqlite_store(tmp_path)
        svc = SystemStatusService(store, config=None)
        resp = svc.config_summary()
        assert resp.status == AppStatus.OK

    def test_provider_status(self, tmp_path: Path) -> None:
        from mind.app.services.system import SystemStatusService

        store = _build_sqlite_store(tmp_path)
        svc = SystemStatusService(store)
        resp = svc.provider_status()
        assert resp.status == AppStatus.OK
        assert resp.result is not None
        assert resp.result["provider"] == "stub"


# ---------------------------------------------------------------------------
# 6. Envelope shape consistency
# ---------------------------------------------------------------------------

class TestEnvelopeShape:
    """Every service response carries request_id."""

    def test_all_responses_have_request_id(self, tmp_path: Path) -> None:
        """Spot check that request_id / status are always set."""
        from mind.app.services.system import SystemStatusService
        from mind.app.services.user_state import UserStateService

        store = _build_sqlite_store(tmp_path)

        responses = [
            UserStateService().resolve_principal(_make_request(input={"principal_id": "u1"})),
            UserStateService().get_runtime_defaults(_make_request()),
            SystemStatusService(store).health(_make_request()),
        ]

        for resp in responses:
            assert resp.request_id is not None
            assert resp.status in AppStatus.__members__.values()
