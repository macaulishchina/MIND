"""Frontend-facing application services."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from os import environ
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError as PydanticValidationError

from mind.app._service_utils import new_response
from mind.app.contracts import AppError, AppErrorCode, AppRequest, AppResponse, AppStatus
from mind.telemetry import JsonlTelemetryRecorder, TelemetryEvent, resolve_dev_telemetry_path

_TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})


class _TelemetryEventSource(Protocol):
    def iter_events(self) -> Sequence[TelemetryEvent]: ...


class FrontendExperienceAppService:
    """Project product app services into the frozen Phase M frontend contracts."""

    def __init__(
        self,
        *,
        memory_ingest_service: Any,
        memory_query_service: Any,
        memory_access_service: Any,
        offline_job_app_service: Any,
    ) -> None:
        self._memory_ingest_service = memory_ingest_service
        self._memory_query_service = memory_query_service
        self._memory_access_service = memory_access_service
        self._offline_job_app_service = offline_job_app_service

    def ingest(self, req: AppRequest) -> AppResponse:
        from mind.frontend.experience import FrontendIngestRequest, build_frontend_ingest_result

        validated = self._validate(req, FrontendIngestRequest)
        if isinstance(validated, AppResponse):
            return validated
        inner_req = req.model_copy(update={"input": validated.model_dump(mode="json")})
        response = self._memory_ingest_service.remember(inner_req)
        return self._project(req, response, build_frontend_ingest_result)

    def retrieve(self, req: AppRequest) -> AppResponse:
        from mind.frontend.experience import FrontendRetrieveRequest, build_frontend_retrieve_result

        validated = self._validate(req, FrontendRetrieveRequest)
        if isinstance(validated, AppResponse):
            return validated

        filters: dict[str, Any] = {}
        if validated.episode_id is not None:
            filters["episode_id"] = validated.episode_id
        inner_req = req.model_copy(
            update={
                "input": {
                    "query": validated.query,
                    "query_modes": list(validated.query_modes),
                    "max_candidates": validated.max_candidates,
                    "filters": filters,
                }
            }
        )
        response = self._memory_query_service.recall(inner_req)
        return self._project(req, response, build_frontend_retrieve_result)

    def access(self, req: AppRequest) -> AppResponse:
        from mind.frontend.experience import FrontendAccessRequest, build_frontend_access_result

        validated = self._validate(req, FrontendAccessRequest)
        if isinstance(validated, AppResponse):
            return validated

        requested_mode = "recall" if validated.depth == "focus" else validated.depth
        inner_input: dict[str, Any] = {
            "query": validated.query,
            "mode": requested_mode,
            "query_modes": list(validated.query_modes),
        }
        if validated.episode_id is not None:
            inner_input["episode_id"] = validated.episode_id
        if validated.task_id is not None:
            inner_input["task_id"] = validated.task_id
        inner_req = req.model_copy(update={"input": inner_input})
        response = (
            self._memory_access_service.explain_access(inner_req)
            if validated.explain
            else self._memory_access_service.run_access(inner_req)
        )
        return self._project(req, response, build_frontend_access_result)

    def submit_offline(self, req: AppRequest) -> AppResponse:
        from mind.frontend.experience import (
            FrontendOfflineSubmitRequest,
            build_frontend_offline_submit_result,
        )

        validated = self._validate(req, FrontendOfflineSubmitRequest)
        if isinstance(validated, AppResponse):
            return validated
        inner_req = req.model_copy(update={"input": validated.model_dump(mode="json")})
        response = self._offline_job_app_service.submit_job(inner_req)
        return self._project(req, response, build_frontend_offline_submit_result)

    def gate_demo(self, req: AppRequest) -> AppResponse:
        from mind.frontend.experience import build_frontend_gate_demo_page

        response = new_response(req)
        response.status = AppStatus.OK
        response.result = build_frontend_gate_demo_page().model_dump(mode="json")
        return response

    def _project(
        self,
        req: AppRequest,
        response: AppResponse,
        projector: Any,
    ) -> AppResponse:
        if response.status is not AppStatus.OK or response.result is None:
            return response
        projected = new_response(req)
        projected.status = AppStatus.OK
        projected.result = projector(response).model_dump(mode="json")
        projected.trace_ref = response.trace_ref
        return projected

    def _validate(self, req: AppRequest, model_type: Any) -> Any:
        try:
            return model_type.model_validate(req.input)
        except PydanticValidationError as exc:
            response = new_response(req)
            response.status = AppStatus.ERROR
            response.error = AppError(
                code=AppErrorCode.VALIDATION_ERROR,
                message="request validation failed",
                details={"errors": [dict(error) for error in exc.errors()]},
            )
            return response


class FrontendSettingsAppService:
    """Frontend-facing settings reads and explicit apply/restore lifecycle."""

    def __init__(
        self,
        *,
        system_status_service: Any,
        user_state_service: Any,
        current_config: Any,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._system_status_service = system_status_service
        self._user_state_service = user_state_service
        self._current_config = current_config
        self._env = env

    def get_page(self, req: AppRequest) -> AppResponse:
        response = new_response(req)
        response.status = AppStatus.OK
        response.result = self._build_settings_page(req).model_dump(mode="json")
        return response

    def preview(self, req: AppRequest) -> AppResponse:
        from mind.frontend.settings import preview_frontend_settings_update

        preview = preview_frontend_settings_update(
            req.input,
            current_config=self._current_config,
            env=self._env,
        )
        response = new_response(req)
        response.status = AppStatus.OK
        response.result = preview.model_dump(mode="json")
        return response

    def apply(self, req: AppRequest) -> AppResponse:
        from mind.frontend.settings import (
            build_frontend_settings_mutation_result,
            build_frontend_settings_snapshot,
            dump_frontend_settings_snapshot_state,
            load_frontend_settings_snapshot_state,
            preview_frontend_settings_update,
        )

        preview = preview_frontend_settings_update(
            req.input,
            current_config=self._current_config,
            env=self._env,
        )
        current_state = load_frontend_settings_snapshot_state(self._current_preferences(req))
        current_snapshot = build_frontend_settings_snapshot(
            preview,
            snapshot_id=req.request_id,
            action="apply",
        )
        self._persist_snapshot_state(
            req,
            dump_frontend_settings_snapshot_state(
                {
                    "current_snapshot": current_snapshot,
                    "previous_snapshot": current_state.current_snapshot,
                }
            ),
        )
        mutation = build_frontend_settings_mutation_result(
            action="apply",
            current_snapshot=current_snapshot,
            previous_snapshot=current_state.current_snapshot,
            preview=preview,
        )
        response = new_response(req)
        response.status = AppStatus.OK
        response.result = mutation.model_dump(mode="json")
        return response

    def restore(self, req: AppRequest) -> AppResponse:
        from mind.frontend.settings import (
            build_frontend_settings_mutation_result,
            build_frontend_settings_snapshot,
            dump_frontend_settings_snapshot_state,
            load_frontend_settings_snapshot_state,
            preview_frontend_settings_update,
        )

        current_state = load_frontend_settings_snapshot_state(self._current_preferences(req))
        if current_state.previous_snapshot is None:
            response = new_response(req)
            response.status = AppStatus.ERROR
            response.error = AppError(
                code=AppErrorCode.NOT_FOUND,
                message="no previous frontend settings snapshot is available to restore",
            )
            return response

        preview = preview_frontend_settings_update(
            current_state.previous_snapshot.request.model_dump(mode="json"),
            current_config=self._current_config,
            env=self._env,
        )
        restored_snapshot = build_frontend_settings_snapshot(
            preview,
            snapshot_id=req.request_id,
            action="restore",
        )
        self._persist_snapshot_state(
            req,
            dump_frontend_settings_snapshot_state(
                {
                    "current_snapshot": restored_snapshot,
                    "previous_snapshot": current_state.current_snapshot,
                }
            ),
        )
        mutation = build_frontend_settings_mutation_result(
            action="restore",
            current_snapshot=restored_snapshot,
            previous_snapshot=current_state.current_snapshot,
            preview=preview,
        )
        response = new_response(req)
        response.status = AppStatus.OK
        response.result = mutation.model_dump(mode="json")
        return response

    def _build_settings_page(self, req: AppRequest) -> Any:
        from mind.frontend.settings import (
            build_frontend_settings_page,
            load_frontend_settings_snapshot_state,
        )

        config_response = self._system_status_service.config_summary(req)
        provider_response = self._system_status_service.provider_status(req)
        if config_response.status is not AppStatus.OK or config_response.result is None:
            raise RuntimeError("config summary is unavailable")
        if provider_response.status is not AppStatus.OK or provider_response.result is None:
            raise RuntimeError("provider status is unavailable")
        return build_frontend_settings_page(
            config_response.result,
            provider_response.result,
            snapshot_state=load_frontend_settings_snapshot_state(self._current_preferences(req)),
        )

    def _current_preferences(self, req: AppRequest) -> Mapping[str, Any]:
        principal_response = self._user_state_service.get_principal(
            req.model_copy(update={"input": {"principal_id": self._principal_id(req)}})
        )
        if principal_response.status is not AppStatus.OK or principal_response.result is None:
            return {}
        preferences = principal_response.result.get("preferences", {})
        return preferences if isinstance(preferences, Mapping) else {}

    def _persist_snapshot_state(self, req: AppRequest, preference_update: Mapping[str, Any]) -> None:
        principal_id = self._principal_id(req)
        self._user_state_service.resolve_principal(
            req.model_copy(update={"input": {"principal_id": principal_id}})
        )
        update_response = self._user_state_service.update_user_preferences(
            req.model_copy(
                update={
                    "input": {
                        "principal_id": principal_id,
                        "preferences": dict(preference_update),
                    }
                }
            )
        )
        if update_response.status is not AppStatus.OK:
            raise RuntimeError("unable to persist frontend settings snapshot state")

    @staticmethod
    def _principal_id(req: AppRequest) -> str:
        if req.principal is not None:
            return req.principal.principal_id
        return "frontend-user"


class FrontendDebugAppService:
    """Resolve and query telemetry-backed debug timelines for frontend consumers."""

    def __init__(
        self,
        *,
        telemetry_source: _TelemetryEventSource | None = None,
        telemetry_path: str | Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._telemetry_source = telemetry_source
        self._telemetry_path = resolve_dev_telemetry_path(telemetry_path=telemetry_path, env=env)
        self._env = env

    def query_timeline(
        self,
        query: Any,
        *,
        dev_mode: bool | None = None,
    ) -> Any:
        """Return a frontend-facing debug timeline."""

        from mind.frontend.debug import build_frontend_debug_timeline

        return build_frontend_debug_timeline(
            self._iter_events(),
            query,
            dev_mode=self._resolve_dev_mode(dev_mode),
        )

    def _iter_events(self) -> Sequence[TelemetryEvent]:
        if self._telemetry_source is not None:
            return tuple(self._telemetry_source.iter_events())
        if self._telemetry_path is None:
            return ()
        return JsonlTelemetryRecorder(self._telemetry_path).iter_events()

    def _resolve_dev_mode(self, override: bool | None) -> bool:
        if override is not None:
            return override
        active_env = self._env or environ
        return active_env.get("MIND_DEV_MODE", "").strip().lower() in _TRUE_ENV_VALUES
