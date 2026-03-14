"""Frontend-facing application services."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from os import environ
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError as PydanticValidationError

from mind.app._service_utils import new_response
from mind.app.contracts import AppError, AppErrorCode, AppRequest, AppResponse, AppStatus
from mind.app.runtime import SYSTEM_RUNTIME_PRINCIPAL_ID, GlobalRuntimeManager
from mind.app.services.system import build_config_summary_payload, build_provider_status_payload
from mind.capabilities import resolve_capability_provider_config
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
        request_defaults_resolver: Any = None,
    ) -> None:
        self._memory_ingest_service = memory_ingest_service
        self._memory_query_service = memory_query_service
        self._memory_access_service = memory_access_service
        self._offline_job_app_service = offline_job_app_service
        self._request_defaults_resolver = request_defaults_resolver

    def ingest(self, req: AppRequest) -> AppResponse:
        from mind.frontend.experience import FrontendIngestRequest, build_frontend_ingest_result

        req = self._apply_request_defaults(req, include_provider_selection=False)
        validated = self._validate(req, FrontendIngestRequest)
        if isinstance(validated, AppResponse):
            return validated
        inner_req = req.model_copy(update={"input": validated.model_dump(mode="json")})
        response = self._memory_ingest_service.remember(inner_req)
        return self._project(req, response, build_frontend_ingest_result)

    def retrieve(self, req: AppRequest) -> AppResponse:
        from mind.frontend.experience import FrontendRetrieveRequest, build_frontend_retrieve_result

        req = self._apply_request_defaults(req, include_provider_selection=False)
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

        req = self._apply_request_defaults(req, include_provider_selection=True)
        validated = self._validate(req, FrontendAccessRequest)
        if isinstance(validated, AppResponse):
            return validated

        requested_mode = "recall" if validated.depth == "focus" else validated.depth
        inner_input: dict[str, Any] = {
            "query": validated.query,
            "mode": requested_mode,
            "query_modes": list(validated.query_modes),
            "capture_raw_exchange": True,
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
        return self._project(
            req,
            response,
            lambda projected_response: build_frontend_access_result(
                projected_response,
                frontend_request=validated,
                runtime_provider=(
                    req.provider_selection.provider if req.provider_selection is not None else None
                ),
            ),
        )

    def submit_offline(self, req: AppRequest) -> AppResponse:
        from mind.frontend.experience import (
            FrontendOfflineSubmitRequest,
            build_frontend_offline_submit_result,
        )

        req = self._apply_request_defaults(req, include_provider_selection=True)
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

    def _apply_request_defaults(
        self,
        req: AppRequest,
        *,
        include_provider_selection: bool,
    ) -> AppRequest:
        if self._request_defaults_resolver is None:
            return req
        return self._request_defaults_resolver(
            req,
            include_provider_selection=include_provider_selection,
            respect_request_policy=True,
        )

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
        runtime_manager: GlobalRuntimeManager,
    ) -> None:
        self._system_status_service = system_status_service
        self._user_state_service = user_state_service
        self._current_config = current_config
        self._runtime_manager = runtime_manager

    def get_page(self, req: AppRequest) -> AppResponse:
        self._runtime_manager.bootstrap()
        response = new_response(req)
        response.status = AppStatus.OK
        response.result = self._build_settings_page(req).model_dump(mode="json")
        return response

    def preview(self, req: AppRequest) -> AppResponse:
        from mind.frontend.settings import (
            load_frontend_llm_state,
            preview_frontend_settings_update,
        )

        self._runtime_manager.bootstrap()
        preferences = self._current_preferences()
        preview = preview_frontend_settings_update(
            req.input,
            current_config=self._current_config,
            env=self.current_provider_env(),
            llm_state=load_frontend_llm_state(preferences),
        )
        response = new_response(req)
        response.status = AppStatus.OK
        response.result = preview.model_dump(mode="json")
        return response

    def apply(self, req: AppRequest) -> AppResponse:
        from mind.frontend.settings import (
            apply_frontend_llm_state_update,
            build_frontend_settings_mutation_result,
            build_frontend_settings_snapshot,
            dump_frontend_llm_state,
            dump_frontend_settings_snapshot_state,
            load_frontend_llm_state,
            load_frontend_settings_snapshot_state,
            preview_frontend_settings_update,
        )

        self._runtime_manager.bootstrap()
        preferences = self._current_preferences()
        current_llm_state = load_frontend_llm_state(preferences)
        preview = preview_frontend_settings_update(
            req.input,
            current_config=self._current_config,
            env=self.current_provider_env(),
            llm_state=current_llm_state,
        )
        next_llm_state = apply_frontend_llm_state_update(current_llm_state, preview.request)
        current_state = load_frontend_settings_snapshot_state(preferences)
        current_snapshot = build_frontend_settings_snapshot(
            preview,
            snapshot_id=req.request_id,
            action="apply",
        )
        self._persist_preferences(
            {
                **dump_frontend_settings_snapshot_state(
                    {
                        "current_snapshot": current_snapshot,
                        "previous_snapshot": current_state.current_snapshot,
                    }
                ),
                **dump_frontend_llm_state(next_llm_state),
            },
        )
        mutation = build_frontend_settings_mutation_result(
            action="apply",
            current_snapshot=current_snapshot,
            previous_snapshot=current_state.current_snapshot,
            preview=preview,
        )
        self._runtime_manager.apply_update_request(
            preview.request,
            llm_state=next_llm_state,
            source="persisted",
            source_service_id=preview.request.service_id,
        )
        response = new_response(req)
        response.status = AppStatus.OK
        response.result = mutation.model_dump(mode="json")
        return response

    def restore(self, req: AppRequest) -> AppResponse:
        from mind.frontend.settings import (
            apply_frontend_llm_state_update,
            build_frontend_settings_mutation_result,
            build_frontend_settings_snapshot,
            dump_frontend_llm_state,
            dump_frontend_settings_snapshot_state,
            load_frontend_llm_state,
            load_frontend_settings_snapshot_state,
            preview_frontend_settings_update,
        )

        self._runtime_manager.bootstrap()
        preferences = self._current_preferences()
        current_llm_state = load_frontend_llm_state(preferences)
        current_state = load_frontend_settings_snapshot_state(preferences)
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
            env=self.current_provider_env(),
            llm_state=current_llm_state,
        )
        next_llm_state = apply_frontend_llm_state_update(current_llm_state, preview.request)
        restored_snapshot = build_frontend_settings_snapshot(
            preview,
            snapshot_id=req.request_id,
            action="restore",
        )
        self._persist_preferences(
            {
                **dump_frontend_settings_snapshot_state(
                    {
                        "current_snapshot": restored_snapshot,
                        "previous_snapshot": current_state.current_snapshot,
                    }
                ),
                **dump_frontend_llm_state(next_llm_state),
            },
        )
        mutation = build_frontend_settings_mutation_result(
            action="restore",
            current_snapshot=restored_snapshot,
            previous_snapshot=current_state.current_snapshot,
            preview=preview,
        )
        self._runtime_manager.apply_update_request(
            preview.request,
            llm_state=next_llm_state,
            source="persisted",
            source_service_id=preview.request.service_id,
        )
        response = new_response(req)
        response.status = AppStatus.OK
        response.result = mutation.model_dump(mode="json")
        return response

    def upsert_llm_service(self, req: AppRequest) -> AppResponse:
        from mind.frontend.settings import (
            FrontendLlmServiceMutationResult,
            FrontendLlmServiceUpsertRequest,
            dump_frontend_llm_state,
            load_frontend_llm_state,
            upsert_frontend_llm_service,
        )

        validated = self._validate_payload(req, FrontendLlmServiceUpsertRequest)
        if isinstance(validated, AppResponse):
            return validated

        self._runtime_manager.bootstrap()
        preferences = self._current_preferences()
        current_llm_state = load_frontend_llm_state(preferences)
        next_llm_state, service, action = upsert_frontend_llm_service(
            current_llm_state,
            validated,
            new_service_id=req.request_id,
        )
        self._persist_preferences(dump_frontend_llm_state(next_llm_state))
        if current_llm_state.get("active_service_id") == service["service_id"]:
            self._runtime_manager.update_active_service(
                service,
                llm_state=next_llm_state,
                source="persisted",
            )
        response = new_response(req)
        response.status = AppStatus.OK
        response.result = FrontendLlmServiceMutationResult(
            action=action,
            service_id=str(service["service_id"]),
        ).model_dump(mode="json")
        return response

    def discover_llm_models(self, req: AppRequest) -> AppResponse:
        from mind.frontend.settings import (
            FrontendLlmModelDiscoveryRequest,
            FrontendLlmModelDiscoveryResult,
            discover_frontend_llm_models,
            dump_frontend_llm_state,
            find_frontend_llm_service,
            load_frontend_llm_state,
            remember_frontend_llm_models,
        )

        validated = self._validate_payload(req, FrontendLlmModelDiscoveryRequest)
        if isinstance(validated, AppResponse):
            return validated

        self._runtime_manager.bootstrap()
        preferences = self._current_preferences()
        current_llm_state = load_frontend_llm_state(preferences)
        service = find_frontend_llm_service(current_llm_state, service_id=validated.service_id)
        if service is None:
            response = new_response(req)
            response.status = AppStatus.ERROR
            response.error = AppError(
                code=AppErrorCode.NOT_FOUND,
                message="requested llm service was not found",
            )
            return response
        try:
            models = discover_frontend_llm_models(service)
            next_llm_state, updated_service = remember_frontend_llm_models(
                current_llm_state,
                service_id=validated.service_id,
                models=models,
            )
        except RuntimeError as exc:
            response = new_response(req)
            response.status = AppStatus.ERROR
            response.error = AppError(
                code=AppErrorCode.VALIDATION_ERROR,
                message=str(exc),
            )
            return response

        self._persist_preferences(dump_frontend_llm_state(next_llm_state))
        response = new_response(req)
        response.status = AppStatus.OK
        response.result = FrontendLlmModelDiscoveryResult(
            service_id=str(updated_service["service_id"]),
            protocol=str(updated_service["protocol"]),
            endpoint=str(updated_service["endpoint"]),
            models=[str(item) for item in updated_service["model_options"]],
            active_model=(
                str(updated_service["active_model"])
                if updated_service.get("active_model") is not None
                else None
            ),
        ).model_dump(mode="json")
        return response

    def activate_llm_service(self, req: AppRequest) -> AppResponse:
        from mind.frontend.settings import (
            FrontendLlmServiceActivateRequest,
            FrontendLlmServiceActivationResult,
            activate_frontend_llm_service,
            dump_frontend_llm_state,
            load_frontend_llm_state,
        )

        validated = self._validate_payload(req, FrontendLlmServiceActivateRequest)
        if isinstance(validated, AppResponse):
            return validated

        self._runtime_manager.bootstrap()
        preferences = self._current_preferences()
        current_llm_state = load_frontend_llm_state(preferences)
        try:
            next_llm_state, activated_service = activate_frontend_llm_service(
                current_llm_state,
                validated,
            )
        except RuntimeError as exc:
            response = new_response(req)
            response.status = AppStatus.ERROR
            response.error = AppError(
                code=AppErrorCode.VALIDATION_ERROR,
                message=str(exc),
            )
            return response

        self._persist_preferences(dump_frontend_llm_state(next_llm_state))
        self._runtime_manager.apply_service(
            activated_service,
            llm_state=next_llm_state,
            source="persisted",
        )
        response = new_response(req)
        response.status = AppStatus.OK
        response.result = FrontendLlmServiceActivationResult(
            service_id=str(activated_service["service_id"]),
            protocol=str(activated_service["protocol"]),
            model=str(activated_service["active_model"]),
        ).model_dump(mode="json")
        return response

    def delete_llm_service(self, req: AppRequest) -> AppResponse:
        from mind.frontend.settings import (
            FrontendLlmServiceDeleteRequest,
            FrontendLlmServiceMutationResult,
            delete_frontend_llm_service,
            dump_frontend_llm_state,
            load_frontend_llm_state,
        )

        validated = self._validate_payload(req, FrontendLlmServiceDeleteRequest)
        if isinstance(validated, AppResponse):
            return validated

        self._runtime_manager.bootstrap()
        preferences = self._current_preferences()
        current_llm_state = load_frontend_llm_state(preferences)
        try:
            next_llm_state, deleted_service, deleted_was_active = delete_frontend_llm_service(
                current_llm_state,
                validated,
            )
        except RuntimeError as exc:
            response = new_response(req)
            response.status = AppStatus.ERROR
            response.error = AppError(
                code=AppErrorCode.NOT_FOUND,
                message=str(exc),
            )
            return response

        self._persist_preferences(dump_frontend_llm_state(next_llm_state))
        if deleted_was_active:
            self._runtime_manager.apply_builtin(
                dev_mode=self.current_dev_mode(),
                source="persisted",
            )
        response = new_response(req)
        response.status = AppStatus.OK
        response.result = FrontendLlmServiceMutationResult(
            action="deleted",
            service_id=str(deleted_service["service_id"]),
        ).model_dump(mode="json")
        return response

    def _build_settings_page(self, req: AppRequest) -> Any:
        from mind.frontend.settings import (
            build_frontend_settings_page,
            load_frontend_llm_state,
            load_frontend_settings_snapshot_state,
        )

        self._runtime_manager.bootstrap()
        preferences = self._current_preferences()
        current_provider_selection = self._runtime_manager.current_provider_selection()
        return build_frontend_settings_page(
            build_config_summary_payload(
                self._current_config,
                env=self.current_provider_env(),
            ),
            build_provider_status_payload(
                resolve_capability_provider_config(
                    selection=current_provider_selection,
                    env=self.current_provider_env(),
                )
            ),
            llm_state=load_frontend_llm_state(preferences),
            snapshot_state=load_frontend_settings_snapshot_state(preferences),
            runtime_scope="process",
            runtime_source=self._runtime_manager.current_source(),
            runtime_source_service_id=self._runtime_manager.current_source_service_id(),
        )

    def apply_runtime_defaults(
        self,
        req: AppRequest,
        *,
        include_provider_selection: bool = True,
    ) -> AppRequest:
        return self._runtime_manager.apply_request_defaults(
            req,
            include_provider_selection=include_provider_selection,
        )

    def current_dev_mode(self) -> bool:
        return self._runtime_manager.current_dev_mode()

    def current_provider_env(self) -> Mapping[str, str]:
        return self._runtime_manager.current_provider_env()

    def _current_preferences(self) -> Mapping[str, Any]:
        return self._preferences_for_principal(SYSTEM_RUNTIME_PRINCIPAL_ID)

    def _preferences_for_principal(self, principal_id: str) -> Mapping[str, Any]:
        principal_response = self._user_state_service.get_principal(
            AppRequest(
                request_id=f"frontend-settings-principal-{principal_id}",
                input={"principal_id": principal_id},
            )
        )
        if principal_response.status is not AppStatus.OK or principal_response.result is None:
            return {}
        preferences = principal_response.result.get("preferences", {})
        return preferences if isinstance(preferences, Mapping) else {}

    def _persist_preferences(self, preference_update: Mapping[str, Any]) -> None:
        principal_id = SYSTEM_RUNTIME_PRINCIPAL_ID
        self._user_state_service.resolve_principal(
            AppRequest(
                request_id=f"frontend-settings-resolve-{principal_id}",
                input={"principal_id": principal_id},
            )
        )
        update_response = self._user_state_service.update_user_preferences(
            AppRequest(
                request_id=f"frontend-settings-update-{principal_id}",
                input={
                    "principal_id": principal_id,
                    "preferences": dict(preference_update),
                },
            )
        )
        if update_response.status is not AppStatus.OK:
            raise RuntimeError("unable to persist frontend settings snapshot state")

    @staticmethod
    def _validate_payload(req: AppRequest, model_type: Any) -> Any:
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


class FrontendDebugAppService:
    """Resolve and query telemetry-backed debug timelines for frontend consumers."""

    def __init__(
        self,
        *,
        telemetry_source: _TelemetryEventSource | None = None,
        telemetry_path: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        dev_mode_resolver: Any = None,
    ) -> None:
        self._telemetry_source = telemetry_source
        self._telemetry_path = resolve_dev_telemetry_path(telemetry_path=telemetry_path, env=env)
        self._env = env
        self._dev_mode_resolver = dev_mode_resolver

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
        if self._dev_mode_resolver is not None:
            return bool(self._dev_mode_resolver())
        active_env = self._env or environ
        return active_env.get("MIND_DEV_MODE", "").strip().lower() in _TRUE_ENV_VALUES
