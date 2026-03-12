from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from mind.app.context import ExecutionPolicy, SessionContext
from mind.app.contracts import AppRequest, AppStatus
from mind.app.services.frontend import FrontendDebugAppService
from mind.kernel.store import SQLiteMemoryStore
from mind.primitives.contracts import PrimitiveExecutionContext
from mind.primitives.service import PrimitiveService
from mind.telemetry import InMemoryTelemetryRecorder

FIXED_TIMESTAMP = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)


def _request(input_payload: dict[str, Any], *, request_id: str, dev_mode: bool) -> AppRequest:
    return AppRequest(
        request_id=request_id,
        session=SessionContext(session_id="phase-m-front-service", request_id=request_id),
        policy=ExecutionPolicy(dev_mode=dev_mode),
        input=input_payload,
    )


def _primitive_context(*, run_id: str, dev_mode: bool) -> PrimitiveExecutionContext:
    return PrimitiveExecutionContext(
        actor="phase-m-front-service",
        budget_scope_id="phase-m-front-service",
        capabilities=[],
        dev_mode=dev_mode,
        telemetry_run_id=run_id,
    )


def test_frontend_debug_app_service_rejects_without_dev_mode() -> None:
    service = FrontendDebugAppService()

    with pytest.raises(RuntimeError, match="dev_mode=true"):
        service.query_timeline({"run_id": "run-disabled"}, dev_mode=False)


def test_frontend_debug_app_service_queries_in_memory_recorder(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()

    with SQLiteMemoryStore(tmp_path / "frontend_service.sqlite3") as store:
        primitive = PrimitiveService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        result = primitive.write_raw(
            {
                "record_kind": "user_message",
                "content": "frontend service telemetry",
                "episode_id": "phase-m-frontend-service",
                "timestamp_order": 1,
            },
            _primitive_context(run_id="run-front-service", dev_mode=True),
        )

    assert result.response is not None
    service = FrontendDebugAppService(telemetry_source=recorder)
    response = service.query_timeline(
        {"run_id": "run-front-service", "include_state_deltas": True},
        dev_mode=True,
    )

    assert response.returned_event_count >= 3
    assert any(delta.object_id == result.response["object_id"] for delta in response.object_deltas)


def test_registry_exposes_frontend_debug_service_with_persisted_telemetry(
    tmp_path: Path,
) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    telemetry_path = tmp_path / "telemetry" / "events.jsonl"
    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "frontend_registry.sqlite3"),
        allow_sqlite=True,
    )

    with build_app_registry(
        config,
        telemetry_path=telemetry_path,
        telemetry_recorder=InMemoryTelemetryRecorder(),
    ) as registry:
        remember = registry.memory_ingest_service.remember(
            _request(
                {
                    "content": "registry-backed frontend debug flow",
                    "episode_id": "phase-m-front-registry",
                    "timestamp_order": 1,
                },
                request_id="req-front-registry",
                dev_mode=True,
            )
        )

        assert remember.status is AppStatus.OK
        timeline = registry.frontend_debug_service.query_timeline(
            {"run_id": "req-front-registry", "include_state_deltas": True},
            dev_mode=True,
        )

    assert telemetry_path.exists()
    assert timeline.returned_event_count >= 3
    assert len(timeline.object_deltas) >= 1


def test_registry_exposes_frontend_experience_service(tmp_path: Path) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "frontend_experience_registry.sqlite3"),
        allow_sqlite=True,
    )

    with build_app_registry(config) as registry:
        ingest = registry.frontend_experience_service.ingest(
            _request(
                {
                    "content": "frontend service ingest seed",
                    "episode_id": "phase-m-front-experience",
                    "timestamp_order": 1,
                },
                request_id="req-front-experience-ingest",
                dev_mode=False,
            )
        )
        assert ingest.status is AppStatus.OK
        assert ingest.result is not None

        retrieve = registry.frontend_experience_service.retrieve(
            _request(
                {
                    "query": "frontend service ingest",
                    "episode_id": "phase-m-front-experience",
                    "max_candidates": 5,
                },
                request_id="req-front-experience-retrieve",
                dev_mode=False,
            )
        )
        access = registry.frontend_experience_service.access(
            _request(
                {
                    "query": "frontend service ingest seed",
                    "episode_id": "phase-m-front-experience",
                    "depth": "focus",
                    "explain": True,
                },
                request_id="req-front-experience-access",
                dev_mode=False,
            )
        )
        offline = registry.frontend_experience_service.submit_offline(
            _request(
                {
                    "job_kind": "reflect_episode",
                    "payload": {
                        "episode_id": "phase-m-front-experience",
                        "focus": "frontend service job",
                    },
                },
                request_id="req-front-experience-offline",
                dev_mode=False,
            )
        )

    assert retrieve.status is AppStatus.OK
    assert retrieve.result is not None
    assert retrieve.result["candidate_count"] >= 1
    assert retrieve.result["candidates"][0]["object_id"] == ingest.result["object_id"]

    assert access.status is AppStatus.OK
    assert access.result is not None
    assert access.result["resolved_depth"] == "focus"
    assert access.result["candidate_count"] >= 1
    assert access.result["answer"]["text"]
    assert access.result["answer"]["support_ids"]

    assert offline.status is AppStatus.OK
    assert offline.result == {"job_id": offline.result["job_id"], "status": "pending"}


def test_frontend_experience_service_ingest_generates_episode_id_when_omitted(
    tmp_path: Path,
) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "frontend_experience_optional_episode.sqlite3"),
        allow_sqlite=True,
    )

    with build_app_registry(config) as registry:
        ingest = registry.frontend_experience_service.ingest(
            _request(
                {"content": "frontend service ingest without explicit episode"},
                request_id="req-front-experience-ingest-no-episode",
                dev_mode=False,
            )
        )

    assert ingest.status is AppStatus.OK
    assert ingest.result is not None
    assert ingest.result["object_id"].startswith("raw-")
    assert ingest.result["episode_id"].startswith("ep-")


def test_frontend_experience_service_returns_validation_error_for_bad_payload(
    tmp_path: Path,
) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "frontend_experience_validation.sqlite3"),
        allow_sqlite=True,
    )

    with build_app_registry(config) as registry:
        response = registry.frontend_experience_service.ingest(
            _request(
                {"content": "   "},
                request_id="req-front-experience-invalid",
                dev_mode=False,
            )
        )

    assert response.status is AppStatus.ERROR
    assert response.error is not None
    assert response.error.code.value == "validation_error"


def test_registry_exposes_frontend_gate_demo_service(tmp_path: Path) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "frontend_gate_demo_registry.sqlite3"),
        allow_sqlite=True,
    )

    with build_app_registry(config) as registry:
        response = registry.frontend_experience_service.gate_demo(
            _request({}, request_id="req-front-gate-demo", dev_mode=False)
        )

    assert response.status is AppStatus.OK
    assert response.result is not None
    assert response.result["page_version"] == "FrontendGateDemoPage v1"
    assert len(response.result["entries"]) == 7


def test_registry_exposes_frontend_settings_apply_and_restore(tmp_path: Path) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "frontend_settings_registry.sqlite3"),
        allow_sqlite=True,
    )

    with build_app_registry(config) as registry:
        initial_page = registry.frontend_settings_service.get_page(
            _request({}, request_id="req-front-settings-page", dev_mode=False)
        )
        assert initial_page.status is AppStatus.OK
        assert initial_page.result is not None
        assert initial_page.result["snapshot_state"]["restore_available"] is False

        first_apply = registry.frontend_settings_service.apply(
            _request(
                {"provider": "openai", "model": "gpt-4.1-mini"},
                request_id="req-front-settings-apply-1",
                dev_mode=False,
            )
        )
        second_apply = registry.frontend_settings_service.apply(
            _request(
                {"profile": "postgres_main", "dev_mode": True},
                request_id="req-front-settings-apply-2",
                dev_mode=False,
            )
        )
        restored = registry.frontend_settings_service.restore(
            _request({}, request_id="req-front-settings-restore", dev_mode=False)
        )
        persisted_page = registry.frontend_settings_service.get_page(
            _request({}, request_id="req-front-settings-page-2", dev_mode=False)
        )

    assert first_apply.status is AppStatus.OK
    assert second_apply.status is AppStatus.OK
    assert restored.status is AppStatus.OK
    assert restored.result is not None
    assert restored.result["action"] == "restore"
    assert restored.result["current_snapshot"]["request"]["provider"] == "openai"
    assert restored.result["previous_snapshot"]["request"]["profile"] == "postgres_main"

    assert persisted_page.result is not None
    assert persisted_page.result["snapshot_state"]["restore_available"] is True
    assert (
        persisted_page.result["snapshot_state"]["current_snapshot"]["snapshot_id"]
        == "req-front-settings-restore"
    )


def test_frontend_settings_restore_requires_previous_snapshot(tmp_path: Path) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "frontend_settings_restore.sqlite3"),
        allow_sqlite=True,
    )

    with build_app_registry(config) as registry:
        response = registry.frontend_settings_service.restore(
            _request({}, request_id="req-front-settings-restore-missing", dev_mode=False)
        )

    assert response.status is AppStatus.ERROR
    assert response.error is not None
    assert response.error.code.value == "not_found"
