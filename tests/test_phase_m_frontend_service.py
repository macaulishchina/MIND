from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

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


@pytest.fixture(autouse=True)
def _isolate_from_repo_config() -> None:  # type: ignore[misc]
    with patch("mind.capabilities.config_file.load_mind_toml", return_value={}):
        yield


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
    assert offline.result is not None
    assert offline.result == {"job_id": offline.result["job_id"], "status": "pending"}


def test_registry_exposes_frontend_benchmark_launch_and_reload(tmp_path: Path) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "frontend_benchmark_registry.sqlite3"),
        allow_sqlite=True,
    )

    with build_app_registry(config) as registry:
        launched = registry.frontend_experience_service.run_memory_lifecycle_benchmark(
            _request(
                {
                    "dataset_name": "locomo",
                    "source_path": str(
                        Path(__file__).resolve().parent
                        / "data"
                        / "public_datasets"
                        / "locomo_local_slice.json"
                    ),
                },
                request_id="req-front-benchmark-service",
                dev_mode=False,
            )
        )
        reloaded = registry.frontend_experience_service.load_memory_lifecycle_benchmark_report(
            _request({}, request_id="req-front-benchmark-reload", dev_mode=False)
        )

    assert launched.status is AppStatus.OK
    assert launched.result is not None
    assert launched.result["run_id"] == "req-front-benchmark-service"
    assert launched.result["stage_count"] == 5
    assert Path(launched.result["report_path"]).exists()
    assert reloaded.status is AppStatus.OK
    assert reloaded.result is not None
    assert reloaded.result["run_id"] == "req-front-benchmark-service"


def test_frontend_access_uses_activated_openai_compatible_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    captured: dict[str, Any] = {}

    def _fake_transport(
        endpoint: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout_seconds: float | None,
    ) -> dict[str, Any]:
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout_seconds"] = timeout_seconds
        return {
            "id": "chatcmpl_frontend_compatible",
            "model": "deepseek-chat",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"answer_text":"compatible llm answer"}',
                    }
                }
            ],
        }

    monkeypatch.setattr("mind.capabilities.openai_adapter._default_transport", _fake_transport)

    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "frontend_access_openai_compatible.sqlite3"),
        allow_sqlite=True,
    )

    with build_app_registry(config) as registry:
        ingest = registry.frontend_experience_service.ingest(
            _request(
                {
                    "content": "deepseek compatible provider seed",
                    "episode_id": "phase-m-front-compatible",
                    "timestamp_order": 1,
                },
                request_id="req-front-compatible-ingest",
                dev_mode=False,
            )
        )
        assert ingest.status is AppStatus.OK

        upserted = registry.frontend_settings_service.upsert_llm_service(
            _request(
                {
                    "protocol": "openai",
                    "name": "DeepSeek",
                    "endpoint": "https://api.deepseek.com",
                    "api_key": "deepseek-key",
                    "model": "deepseek-chat",
                },
                request_id="req-front-compatible-upsert",
                dev_mode=False,
            )
        )
        assert upserted.status is AppStatus.OK
        assert upserted.result is not None

        activated = registry.frontend_settings_service.activate_llm_service(
            _request(
                {
                    "service_id": upserted.result["service_id"],
                    "model": "deepseek-chat",
                },
                request_id="req-front-compatible-activate",
                dev_mode=False,
            )
        )
        assert activated.status is AppStatus.OK

        access = registry.frontend_experience_service.access(
            _request(
                {
                    "query": "deepseek compatible provider seed",
                    "episode_id": "phase-m-front-compatible",
                    "depth": "focus",
                    "explain": False,
                },
                request_id="req-front-compatible-access",
                dev_mode=False,
            )
        )

    assert access.status is AppStatus.OK
    assert access.result is not None
    assert access.result["answer"]["text"] == "compatible llm answer"
    assert access.result["answer"]["trace"]["provider_family"] == "openai"
    assert (
        access.result["answer"]["trace"]["endpoint"] == "https://api.deepseek.com/chat/completions"
    )
    assert "You are the MIND answer capability." in access.result["answer"]["trace"]["request_text"]
    assert (
        "Question: deepseek compatible provider seed"
        in access.result["answer"]["trace"]["request_text"]
    )
    assert captured["endpoint"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer deepseek-key"
    assert captured["payload"]["messages"][0]["role"] == "user"
    assert "Return JSON only." in captured["payload"]["messages"][0]["content"]


def test_frontend_access_accepts_plain_text_from_openai_compatible_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    def _fake_transport(
        endpoint: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout_seconds: float | None,
    ) -> dict[str, Any]:
        return {
            "id": "chatcmpl_frontend_plain_text",
            "model": "deepseek-chat",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "这是兼容服务直接返回的自然语言回答。",
                    }
                }
            ],
        }

    monkeypatch.setattr("mind.capabilities.openai_adapter._default_transport", _fake_transport)

    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "frontend_access_openai_plain_text.sqlite3"),
        allow_sqlite=True,
    )

    with build_app_registry(config) as registry:
        ingest = registry.frontend_experience_service.ingest(
            _request(
                {
                    "content": "plain text compatible provider seed",
                    "episode_id": "phase-m-front-plain-text",
                    "timestamp_order": 1,
                },
                request_id="req-front-plain-text-ingest",
                dev_mode=False,
            )
        )
        assert ingest.status is AppStatus.OK

        upserted = registry.frontend_settings_service.upsert_llm_service(
            _request(
                {
                    "protocol": "openai",
                    "name": "DeepSeek",
                    "endpoint": "https://api.deepseek.com",
                    "api_key": "deepseek-key",
                    "model": "deepseek-chat",
                },
                request_id="req-front-plain-text-upsert",
                dev_mode=False,
            )
        )
        assert upserted.status is AppStatus.OK
        assert upserted.result is not None

        activated = registry.frontend_settings_service.activate_llm_service(
            _request(
                {
                    "service_id": upserted.result["service_id"],
                    "model": "deepseek-chat",
                },
                request_id="req-front-plain-text-activate",
                dev_mode=False,
            )
        )
        assert activated.status is AppStatus.OK

        access = registry.frontend_experience_service.access(
            _request(
                {
                    "query": "plain text compatible provider seed",
                    "episode_id": "phase-m-front-plain-text",
                    "depth": "focus",
                    "explain": False,
                },
                request_id="req-front-plain-text-access",
                dev_mode=False,
            )
        )

    assert access.status is AppStatus.OK
    assert access.result is not None
    assert access.result["answer"]["text"] == "这是兼容服务直接返回的自然语言回答。"
    assert access.result["answer"]["trace"]["provider_family"] == "openai"
    assert access.result["answer"]["trace"]["fallback_used"] is False


def test_frontend_access_accepts_answer_alias_from_openai_compatible_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    def _fake_transport(
        endpoint: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout_seconds: float | None,
    ) -> dict[str, Any]:
        return {
            "id": "chatcmpl_frontend_answer_alias",
            "model": "deepseek-chat",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"answer":"这是兼容服务返回的 answer 字段。"}',
                    }
                }
            ],
        }

    monkeypatch.setattr("mind.capabilities.openai_adapter._default_transport", _fake_transport)

    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "frontend_access_openai_answer_alias.sqlite3"),
        allow_sqlite=True,
    )

    with build_app_registry(config) as registry:
        ingest = registry.frontend_experience_service.ingest(
            _request(
                {
                    "content": "json alias compatible provider seed",
                    "episode_id": "phase-m-front-answer-alias",
                    "timestamp_order": 1,
                },
                request_id="req-front-answer-alias-ingest",
                dev_mode=False,
            )
        )
        assert ingest.status is AppStatus.OK

        upserted = registry.frontend_settings_service.upsert_llm_service(
            _request(
                {
                    "protocol": "openai",
                    "name": "DeepSeek",
                    "endpoint": "https://api.deepseek.com",
                    "api_key": "deepseek-key",
                    "model": "deepseek-chat",
                },
                request_id="req-front-answer-alias-upsert",
                dev_mode=False,
            )
        )
        assert upserted.status is AppStatus.OK
        assert upserted.result is not None

        activated = registry.frontend_settings_service.activate_llm_service(
            _request(
                {
                    "service_id": upserted.result["service_id"],
                    "model": "deepseek-chat",
                },
                request_id="req-front-answer-alias-activate",
                dev_mode=False,
            )
        )
        assert activated.status is AppStatus.OK

        access = registry.frontend_experience_service.access(
            _request(
                {
                    "query": "json alias compatible provider seed",
                    "episode_id": "phase-m-front-answer-alias",
                    "depth": "focus",
                    "explain": False,
                },
                request_id="req-front-answer-alias-access",
                dev_mode=False,
            )
        )

    assert access.status is AppStatus.OK
    assert access.result is not None
    assert access.result["answer"]["text"] == "这是兼容服务返回的 answer 字段。"
    assert access.result["answer"]["trace"]["provider_family"] == "openai"
    assert access.result["answer"]["trace"]["fallback_used"] is False


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


def test_frontend_experience_service_supports_chinese_keyword_retrieve_and_access(
    tmp_path: Path,
) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "frontend_experience_chinese.sqlite3"),
        allow_sqlite=True,
    )

    with build_app_registry(config) as registry:
        ingest = registry.frontend_experience_service.ingest(
            _request(
                {
                    "content": "你好，今天下雨，记得带伞。",
                    "episode_id": "phase-m-front-cn",
                    "timestamp_order": 1,
                },
                request_id="req-front-cn-ingest",
                dev_mode=False,
            )
        )
        assert ingest.status is AppStatus.OK

        retrieve = registry.frontend_experience_service.retrieve(
            _request(
                {
                    "query": "你好",
                    "episode_id": "phase-m-front-cn",
                    "max_candidates": 5,
                },
                request_id="req-front-cn-retrieve",
                dev_mode=False,
            )
        )
        access = registry.frontend_experience_service.access(
            _request(
                {
                    "query": "你好",
                    "episode_id": "phase-m-front-cn",
                    "depth": "focus",
                    "explain": False,
                },
                request_id="req-front-cn-access",
                dev_mode=False,
            )
        )

    assert retrieve.status is AppStatus.OK
    assert retrieve.result is not None
    assert retrieve.result["candidate_count"] >= 1
    assert retrieve.result["candidates"][0]["content_preview"]

    assert access.status is AppStatus.OK
    assert access.result is not None
    assert access.result["answer"]["text"]
    assert access.result["candidate_count"] >= 1


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


def test_registry_exposes_frontend_settings_runtime_apply(tmp_path: Path) -> None:
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
        initial_runtime_req = registry.frontend_settings_service.apply_runtime_defaults(
            _request({}, request_id="req-front-settings-defaults", dev_mode=False)
        )

        applied = registry.frontend_settings_service.apply(
            _request(
                {"provider": "openai", "model": "gpt-4.1-mini", "dev_mode": True},
                request_id="req-front-settings-apply-live",
                dev_mode=False,
            )
        )
        live_runtime_req = registry.frontend_settings_service.apply_runtime_defaults(
            _request({}, request_id="req-front-settings-defaults-live", dev_mode=False)
        )
        persisted_page = registry.frontend_settings_service.get_page(
            _request({}, request_id="req-front-settings-page-2", dev_mode=False)
        )
        debug_timeline = registry.frontend_debug_service.query_timeline(
            {"run_id": "req-front-settings-runtime"},
        )

    assert initial_runtime_req.provider_selection is not None
    assert initial_runtime_req.provider_selection.provider == "stub"
    assert initial_runtime_req.policy is not None
    assert initial_runtime_req.policy.dev_mode is False
    assert applied.status is AppStatus.OK
    assert persisted_page.result is not None
    assert persisted_page.result["provider"]["provider"] == "openai"
    assert persisted_page.result["runtime"]["dev_mode"] is True
    assert live_runtime_req.provider_selection is not None
    assert live_runtime_req.provider_selection.provider == "openai"
    assert live_runtime_req.policy is not None
    assert live_runtime_req.policy.dev_mode is True
    assert len(debug_timeline.timeline) == 0


def test_frontend_settings_apply_persists_llm_endpoint_and_api_key(tmp_path: Path) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "frontend_settings_llm_overrides.sqlite3"),
        allow_sqlite=True,
    )

    with build_app_registry(config) as registry:
        applied = registry.frontend_settings_service.apply(
            _request(
                {
                    "provider": "claude",
                    "model": "claude-3-7-sonnet",
                    "endpoint": "https://proxy.example/v1/messages",
                    "api_key": "anthropic-test-key",
                },
                request_id="req-front-settings-apply-llm-overrides",
                dev_mode=False,
            )
        )
        page = registry.frontend_settings_service.get_page(
            _request({}, request_id="req-front-settings-page-llm-overrides", dev_mode=False)
        )
        runtime_req = registry.frontend_settings_service.apply_runtime_defaults(
            _request({}, request_id="req-front-settings-runtime-llm-overrides", dev_mode=False)
        )

    assert applied.status is AppStatus.OK
    assert page.status is AppStatus.OK
    assert page.result is not None
    assert page.result["provider"]["provider"] == "claude"
    assert page.result["provider"]["endpoint"] == "https://proxy.example/v1/messages"
    service_view = next(
        item for item in page.result["llm"]["services"] if item["protocol"] == "claude"
    )
    assert service_view["service_id"] == "managed-claude"
    assert service_view["active_model"] == "claude-3-7-sonnet"
    assert service_view["endpoint"] == "https://proxy.example/v1"
    assert service_view["uses_official_endpoint"] is False
    assert service_view["api_key_saved"] is True
    assert service_view["api_key_masked"] == "anth***-key"
    assert runtime_req.provider_selection is not None
    assert runtime_req.provider_selection.provider == "claude"
    assert runtime_req.provider_selection.endpoint == "https://proxy.example/v1/messages"


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


def test_frontend_llm_service_lifecycle_persists_and_activates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    class _FakeResponse:
        def __init__(self, payload: dict[str, Any]) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    def _fake_urlopen(request: Any, timeout: float = 10.0) -> _FakeResponse:
        assert request.full_url == "https://proxy.example/v1/models"
        assert timeout == 10.0
        return _FakeResponse({"data": [{"id": "gpt-4.1-mini"}, {"id": "gpt-4o-mini"}]})

    monkeypatch.setattr("mind.app.frontend_llm_services.urlopen", _fake_urlopen)

    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "frontend_llm_service_lifecycle.sqlite3"),
        allow_sqlite=True,
    )

    with build_app_registry(config) as registry:
        upserted = registry.frontend_settings_service.upsert_llm_service(
            _request(
                {
                    "protocol": "openai",
                    "name": "公司代理",
                    "endpoint": "https://proxy.example/v1/responses",
                    "api_key": "proxy-key",
                },
                request_id="req-front-llm-upsert",
                dev_mode=False,
            )
        )
        assert upserted.status is AppStatus.OK
        assert upserted.result is not None

        discovered = registry.frontend_settings_service.discover_llm_models(
            _request(
                {"service_id": upserted.result["service_id"]},
                request_id="req-front-llm-discover",
                dev_mode=False,
            )
        )
        activated = registry.frontend_settings_service.activate_llm_service(
            _request(
                {
                    "service_id": upserted.result["service_id"],
                    "model": "gpt-4o-mini",
                },
                request_id="req-front-llm-activate",
                dev_mode=False,
            )
        )
        page = registry.frontend_settings_service.get_page(
            _request({}, request_id="req-front-llm-page", dev_mode=False)
        )
        runtime_req = registry.frontend_settings_service.apply_runtime_defaults(
            _request({}, request_id="req-front-llm-runtime", dev_mode=False)
        )

    assert discovered.status is AppStatus.OK
    assert discovered.result is not None
    assert discovered.result["models"] == ["gpt-4.1-mini", "gpt-4o-mini"]
    assert activated.status is AppStatus.OK
    assert activated.result == {
        "service_id": upserted.result["service_id"],
        "protocol": "openai",
        "model": "gpt-4o-mini",
    }
    assert page.status is AppStatus.OK
    assert page.result is not None
    assert page.result["provider"]["provider"] == "openai"
    assert page.result["llm"]["active_service_id"] == upserted.result["service_id"]
    service_view = next(
        item
        for item in page.result["llm"]["services"]
        if item["service_id"] == upserted.result["service_id"]
    )
    assert service_view["name"] == "公司代理"
    assert service_view["active_model"] == "gpt-4o-mini"
    assert service_view["endpoint"] == "https://proxy.example/v1"
    assert service_view["model_options"] == ["gpt-4.1-mini", "gpt-4o-mini"]
    assert service_view["uses_official_endpoint"] is False
    assert runtime_req.provider_selection is not None
    assert runtime_req.provider_selection.provider == "openai"
    assert runtime_req.provider_selection.endpoint == "https://proxy.example/v1/chat/completions"
    assert runtime_req.provider_selection.model == "gpt-4o-mini"


def test_active_frontend_llm_service_restores_live_runtime_after_restart(
    tmp_path: Path,
) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    sqlite_path = tmp_path / "frontend_llm_runtime_restore.sqlite3"
    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(sqlite_path),
        allow_sqlite=True,
    )

    service_id: str
    with build_app_registry(config) as registry:
        upserted = registry.frontend_settings_service.upsert_llm_service(
            _request(
                {
                    "protocol": "openai",
                    "name": "DeepSeek",
                    "endpoint": "https://api.deepseek.com/v1",
                    "api_key": "deepseek-live-key",
                    "model": "deepseek-chat",
                },
                request_id="req-front-llm-runtime-restore-upsert",
                dev_mode=False,
            )
        )
        assert upserted.status is AppStatus.OK
        assert upserted.result is not None
        service_id = str(upserted.result["service_id"])

        activated = registry.frontend_settings_service.activate_llm_service(
            _request(
                {
                    "service_id": service_id,
                    "model": "deepseek-chat",
                },
                request_id="req-front-llm-runtime-restore-activate",
                dev_mode=False,
            )
        )
        assert activated.status is AppStatus.OK

    with build_app_registry(config) as rebuilt:
        page = rebuilt.frontend_settings_service.get_page(
            _request({}, request_id="req-front-llm-runtime-restore-page", dev_mode=False)
        )
        runtime_req = rebuilt.frontend_settings_service.apply_runtime_defaults(
            _request({}, request_id="req-front-llm-runtime-restore-runtime", dev_mode=False)
        )
        provider_env = rebuilt.frontend_settings_service.current_provider_env()

    assert page.status is AppStatus.OK
    assert page.result is not None
    assert page.result["provider"]["provider"] == "openai"
    assert page.result["provider"]["model"] == "deepseek-chat"
    assert page.result["provider"]["endpoint"] == "https://api.deepseek.com/v1/chat/completions"
    assert page.result["llm"]["active_service_id"] == service_id
    rebuilt_service = next(
        item for item in page.result["llm"]["services"] if item["service_id"] == service_id
    )
    assert rebuilt_service["name"] == "DeepSeek"
    assert rebuilt_service["is_active"] is True
    assert runtime_req.provider_selection is not None
    assert runtime_req.provider_selection.provider == "openai"
    assert runtime_req.provider_selection.model == "deepseek-chat"
    assert runtime_req.provider_selection.endpoint == "https://api.deepseek.com/v1/chat/completions"
    assert provider_env["MIND_PROVIDER"] == "openai"
    assert provider_env["MIND_MODEL"] == "deepseek-chat"
    assert provider_env["MIND_PROVIDER_ENDPOINT"] == "https://api.deepseek.com/v1/chat/completions"
    assert provider_env["OPENAI_API_KEY"] == "deepseek-live-key"


def test_builtin_mode_snapshot_restores_after_restart_without_reactivating_llm(
    tmp_path: Path,
) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    sqlite_path = tmp_path / "frontend_builtin_runtime_restore.sqlite3"
    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(sqlite_path),
        allow_sqlite=True,
    )

    service_id: str
    with build_app_registry(config) as registry:
        upserted = registry.frontend_settings_service.upsert_llm_service(
            _request(
                {
                    "protocol": "openai",
                    "name": "DeepSeek",
                    "endpoint": "https://api.deepseek.com/v1",
                    "api_key": "deepseek-live-key",
                    "model": "deepseek-chat",
                },
                request_id="req-front-builtin-restore-upsert",
                dev_mode=False,
            )
        )
        assert upserted.status is AppStatus.OK
        assert upserted.result is not None
        service_id = str(upserted.result["service_id"])

        activated = registry.frontend_settings_service.activate_llm_service(
            _request(
                {
                    "service_id": service_id,
                    "model": "deepseek-chat",
                },
                request_id="req-front-builtin-restore-activate",
                dev_mode=False,
            )
        )
        assert activated.status is AppStatus.OK

        applied = registry.frontend_settings_service.apply(
            _request(
                {
                    "provider": "stub",
                    "model": "deterministic",
                    "dev_mode": False,
                },
                request_id="req-front-builtin-restore-apply",
                dev_mode=False,
            )
        )
        assert applied.status is AppStatus.OK

    with build_app_registry(config) as rebuilt:
        page = rebuilt.frontend_settings_service.get_page(
            _request({}, request_id="req-front-builtin-restore-page", dev_mode=False)
        )
        runtime_req = rebuilt.frontend_settings_service.apply_runtime_defaults(
            _request({}, request_id="req-front-builtin-restore-runtime", dev_mode=False)
        )
        provider_env = rebuilt.frontend_settings_service.current_provider_env()

    assert page.status is AppStatus.OK
    assert page.result is not None
    assert page.result["provider"]["provider"] == "deterministic"
    assert page.result["provider"]["provider_family"] == "deterministic"
    assert page.result["provider"]["model"] == "deterministic"
    assert page.result["llm"]["active_service_id"] is None
    assert page.result["llm"]["selected_service_id"] == service_id
    assert runtime_req.provider_selection is not None
    assert runtime_req.provider_selection.provider == "deterministic"
    assert runtime_req.provider_selection.model == "deterministic"
    assert provider_env["MIND_PROVIDER"] == "deterministic"
    assert provider_env["MIND_MODEL"] == "deterministic"
    assert "MIND_PROVIDER_ENDPOINT" not in provider_env


def test_editing_saved_llm_service_does_not_change_active_service(tmp_path: Path) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "frontend_llm_service_editing.sqlite3"),
        allow_sqlite=True,
    )

    with build_app_registry(config) as registry:
        primary = registry.frontend_settings_service.upsert_llm_service(
            _request(
                {
                    "protocol": "openai",
                    "name": "主服务",
                    "endpoint": "https://api.deepseek.com",
                    "model": "deepseek-chat",
                },
                request_id="req-front-llm-edit-primary",
                dev_mode=False,
            )
        )
        assert primary.status is AppStatus.OK
        assert primary.result is not None
        activated = registry.frontend_settings_service.activate_llm_service(
            _request(
                {
                    "service_id": primary.result["service_id"],
                    "model": "deepseek-chat",
                },
                request_id="req-front-llm-edit-activate",
                dev_mode=False,
            )
        )
        assert activated.status is AppStatus.OK

        secondary = registry.frontend_settings_service.upsert_llm_service(
            _request(
                {
                    "protocol": "claude",
                    "name": "备用服务",
                    "endpoint": "https://proxy.example/v1/messages",
                },
                request_id="req-front-llm-edit-secondary",
                dev_mode=False,
            )
        )
        assert secondary.status is AppStatus.OK
        assert secondary.result is not None

        edited = registry.frontend_settings_service.upsert_llm_service(
            _request(
                {
                    "service_id": secondary.result["service_id"],
                    "protocol": "claude",
                    "name": "备用服务-已编辑",
                    "icon": (
                        "data:image/webp;base64,UklGRi4AAABXRUJQVlA4"
                        "ICIAAADQAwCdASoIAAIAAUAmJaACdLoAA5gA"
                    ),
                    "endpoint": "https://proxy.example/v1/messages",
                },
                request_id="req-front-llm-edit-secondary-update",
                dev_mode=False,
            )
        )
        page = registry.frontend_settings_service.get_page(
            _request({}, request_id="req-front-llm-edit-page", dev_mode=False)
        )

    assert edited.status is AppStatus.OK
    assert page.status is AppStatus.OK
    assert page.result is not None
    assert page.result["llm"]["active_service_id"] == primary.result["service_id"]
    edited_view = next(
        item
        for item in page.result["llm"]["services"]
        if item["service_id"] == secondary.result["service_id"]
    )
    assert edited_view["name"] == "备用服务-已编辑"
    assert (
        edited_view["icon"]
        == "data:image/webp;base64,UklGRi4AAABXRUJQVlA4ICIAAADQAwCdASoIAAIAAUAmJaACdLoAA5gA"
    )
    assert edited_view["is_active"] is False


def test_editing_active_llm_service_updates_live_runtime_without_changing_activation(
    tmp_path: Path,
) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "frontend_llm_service_edit_active.sqlite3"),
        allow_sqlite=True,
    )

    with build_app_registry(config) as registry:
        primary = registry.frontend_settings_service.upsert_llm_service(
            _request(
                {
                    "protocol": "openai",
                    "name": "OpenAI 官方",
                    "endpoint": "https://api.openai.com/v1",
                    "api_key": "openai-old-key",
                    "model": "gpt-4.1-mini",
                },
                request_id="req-front-llm-active-edit-primary",
                dev_mode=False,
            )
        )
        assert primary.status is AppStatus.OK
        assert primary.result is not None

        activated = registry.frontend_settings_service.activate_llm_service(
            _request(
                {
                    "service_id": primary.result["service_id"],
                    "model": "gpt-4.1-mini",
                },
                request_id="req-front-llm-active-edit-activate",
                dev_mode=False,
            )
        )
        assert activated.status is AppStatus.OK

        edited = registry.frontend_settings_service.upsert_llm_service(
            _request(
                {
                    "service_id": primary.result["service_id"],
                    "protocol": "openai",
                    "name": "OpenAI 官方",
                    "endpoint": "https://api.deepseek.com/v1",
                    "api_key": "deepseek-live-key",
                    "model": "deepseek-chat",
                },
                request_id="req-front-llm-active-edit-update",
                dev_mode=False,
            )
        )
        page = registry.frontend_settings_service.get_page(
            _request({}, request_id="req-front-llm-active-edit-page", dev_mode=False)
        )
        runtime_req = registry.frontend_settings_service.apply_runtime_defaults(
            _request({}, request_id="req-front-llm-active-edit-runtime", dev_mode=False)
        )

    assert edited.status is AppStatus.OK
    assert page.status is AppStatus.OK
    assert page.result is not None
    assert page.result["llm"]["active_service_id"] == primary.result["service_id"]
    service_view = next(
        item
        for item in page.result["llm"]["services"]
        if item["service_id"] == primary.result["service_id"]
    )
    assert service_view["endpoint"] == "https://api.deepseek.com/v1"
    assert service_view["active_model"] == "deepseek-chat"
    assert service_view["is_active"] is True
    assert service_view["api_key_masked"] == "deep***-key"
    assert page.result["provider"]["endpoint"] == "https://api.deepseek.com/v1/chat/completions"
    assert runtime_req.provider_selection is not None
    assert runtime_req.provider_selection.provider == "openai"
    assert runtime_req.provider_selection.model == "deepseek-chat"
    assert runtime_req.provider_selection.endpoint == "https://api.deepseek.com/v1/chat/completions"


def test_deleting_active_llm_service_removes_it_and_falls_back_to_builtin(tmp_path: Path) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "frontend_llm_service_delete.sqlite3"),
        allow_sqlite=True,
    )

    with build_app_registry(config) as registry:
        primary = registry.frontend_settings_service.upsert_llm_service(
            _request(
                {
                    "protocol": "openai",
                    "name": "主服务",
                    "endpoint": "https://api.deepseek.com",
                    "model": "deepseek-chat",
                },
                request_id="req-front-llm-delete-primary",
                dev_mode=False,
            )
        )
        assert primary.status is AppStatus.OK
        assert primary.result is not None

        activated = registry.frontend_settings_service.activate_llm_service(
            _request(
                {
                    "service_id": primary.result["service_id"],
                    "model": "deepseek-chat",
                },
                request_id="req-front-llm-delete-activate",
                dev_mode=False,
            )
        )
        assert activated.status is AppStatus.OK

        secondary = registry.frontend_settings_service.upsert_llm_service(
            _request(
                {
                    "protocol": "claude",
                    "name": "备用服务",
                    "endpoint": "https://proxy.example",
                },
                request_id="req-front-llm-delete-secondary",
                dev_mode=False,
            )
        )
        assert secondary.status is AppStatus.OK
        assert secondary.result is not None

        deleted = registry.frontend_settings_service.delete_llm_service(
            _request(
                {"service_id": primary.result["service_id"]},
                request_id="req-front-llm-delete-active",
                dev_mode=False,
            )
        )
        page = registry.frontend_settings_service.get_page(
            _request({}, request_id="req-front-llm-delete-page", dev_mode=False)
        )
        runtime_req = registry.frontend_settings_service.apply_runtime_defaults(
            _request({}, request_id="req-front-llm-delete-runtime", dev_mode=False)
        )

    assert deleted.status is AppStatus.OK
    assert deleted.result == {
        "action": "deleted",
        "service_id": primary.result["service_id"],
    }
    assert page.status is AppStatus.OK
    assert page.result is not None
    assert page.result["provider"]["provider"] == "deterministic"
    assert page.result["provider"]["provider_family"] == "deterministic"
    assert page.result["llm"]["active_service_id"] is None
    assert page.result["llm"]["selected_service_id"] == secondary.result["service_id"]
    assert all(
        item["service_id"] != primary.result["service_id"]
        for item in page.result["llm"]["services"]
    )
    assert runtime_req.provider_selection is not None
    assert runtime_req.provider_selection.provider == "deterministic"
    assert runtime_req.provider_selection.model == "deterministic"
