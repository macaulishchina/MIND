"""Frontend experience application service."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError as PydanticValidationError

from mind.app._service_utils import new_response
from mind.app.contracts import AppError, AppErrorCode, AppRequest, AppResponse, AppStatus


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
        from mind.app.frontend_experience import FrontendIngestRequest, build_frontend_ingest_result

        req = self._apply_request_defaults(req, include_provider_selection=False)
        validated = self._validate(req, FrontendIngestRequest)
        if isinstance(validated, AppResponse):
            return validated
        inner_req = req.model_copy(update={"input": validated.model_dump(mode="json")})
        response = self._memory_ingest_service.remember(inner_req)
        return self._project(req, response, build_frontend_ingest_result)

    def retrieve(self, req: AppRequest) -> AppResponse:
        from mind.app.frontend_experience import (
            FrontendRetrieveRequest,
            build_frontend_retrieve_result,
        )

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
        from mind.app.frontend_experience import FrontendAccessRequest, build_frontend_access_result

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
        from mind.app.frontend_experience import (
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
        from mind.app.frontend_experience import build_frontend_gate_demo_page

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
