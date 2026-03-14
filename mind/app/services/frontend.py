"""Frontend-facing application services."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from pydantic import ValidationError as PydanticValidationError

from mind.app._service_utils import new_response
from mind.app.contracts import AppError, AppErrorCode, AppRequest, AppResponse, AppStatus
from mind.app.runtime import SYSTEM_RUNTIME_PRINCIPAL_ID, GlobalRuntimeManager
from mind.app.services.frontend_debug_service import (  # noqa: F401
    FrontendDebugAppService,
)
from mind.app.services.frontend_experience_service import (  # noqa: F401
    FrontendExperienceAppService,
)
from mind.app.services.system import build_config_summary_payload, build_provider_status_payload
from mind.capabilities import resolve_capability_provider_config
from mind.telemetry import TelemetryEvent

_TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})


class _TelemetryEventSource(Protocol):
    def iter_events(self) -> Sequence[TelemetryEvent]: ...


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
        from mind.app.frontend_settings import (
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
        from mind.app.frontend_settings import (
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
        from mind.app.frontend_settings import (
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
        from mind.app.frontend_settings import (
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
        from mind.app.frontend_settings import (
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
        from mind.app.frontend_settings import (
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
        from mind.app.frontend_settings import (
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
        from mind.app.frontend_settings import (
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
