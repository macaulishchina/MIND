"""Frontend experience application service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from mind.app._service_utils import new_response
from mind.app.contracts import AppError, AppErrorCode, AppRequest, AppResponse, AppStatus
from mind.app.services._frontend_benchmark_helpers import (
    _resolve_project_root,
    build_benchmark_workspace_payload,
    coerce_list_payload,
    report_to_payload,
    resolve_dataset_selector_values,
)


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
        benchmark_artifact_root: str | Path = "artifacts/dev/memory_lifecycle_benchmark",
    ) -> None:
        self._memory_ingest_service = memory_ingest_service
        self._memory_query_service = memory_query_service
        self._memory_access_service = memory_access_service
        self._offline_job_app_service = offline_job_app_service
        self._request_defaults_resolver = request_defaults_resolver
        self._benchmark_artifact_root = Path(benchmark_artifact_root)

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

    def run_memory_lifecycle_benchmark(self, req: AppRequest) -> AppResponse:
        from mind.app.frontend_experience_benchmark import (
            FrontendMemoryLifecycleBenchmarkLaunchRequest,
            build_frontend_memory_lifecycle_benchmark_result,
        )
        from mind.eval import (
            evaluate_memory_lifecycle_benchmark,
            persist_memory_lifecycle_benchmark_report,
            prepare_memory_lifecycle_benchmark_artifacts,
        )

        req = self._apply_request_defaults(req, include_provider_selection=True)
        validated = self._validate(req, FrontendMemoryLifecycleBenchmarkLaunchRequest)
        if isinstance(validated, AppResponse):
            return validated

        artifacts = prepare_memory_lifecycle_benchmark_artifacts(
            self._benchmark_artifact_root,
            run_id=req.request_id,
        )
        try:
            report = evaluate_memory_lifecycle_benchmark(
                validated.dataset_name,
                source_path=validated.source_path,
                provider_selection=req.provider_selection,
                telemetry_path=artifacts.telemetry_path,
                store_path=artifacts.store_path,
                run_id=req.request_id,
            )
            persist_memory_lifecycle_benchmark_report(artifacts, report)
        except FileNotFoundError as exc:
            return self._error_response(req, AppErrorCode.NOT_FOUND, str(exc))
        except ValueError as exc:
            return self._error_response(req, AppErrorCode.VALIDATION_ERROR, str(exc))
        except RuntimeError as exc:
            return self._error_response(req, AppErrorCode.INTERNAL_ERROR, str(exc))

        response = new_response(req)
        response.status = AppStatus.OK
        response.result = build_frontend_memory_lifecycle_benchmark_result(
            {
                **report_to_payload(report),
                "report_path": str(artifacts.report_path),
            }
        ).model_dump(mode="json")
        return response

    def load_memory_lifecycle_benchmark_report(self, req: AppRequest) -> AppResponse:
        from mind.app.frontend_experience_benchmark import (
            FrontendMemoryLifecycleBenchmarkQueryRequest,
            build_frontend_memory_lifecycle_benchmark_result,
        )
        from mind.eval import load_memory_lifecycle_benchmark_report

        validated = self._validate(req, FrontendMemoryLifecycleBenchmarkQueryRequest)
        if isinstance(validated, AppResponse):
            return validated

        try:
            report, report_path = load_memory_lifecycle_benchmark_report(
                self._benchmark_artifact_root,
                run_id=validated.run_id,
            )
        except FileNotFoundError as exc:
            return self._error_response(req, AppErrorCode.NOT_FOUND, str(exc))
        except ValueError as exc:
            return self._error_response(req, AppErrorCode.VALIDATION_ERROR, str(exc))

        response = new_response(req)
        response.status = AppStatus.OK
        response.result = build_frontend_memory_lifecycle_benchmark_result(
            {
                **report_to_payload(report),
                "report_path": str(report_path),
            }
        ).model_dump(mode="json")
        return response

    def load_memory_lifecycle_benchmark_workspace(self, req: AppRequest) -> AppResponse:
        from mind.app.frontend_experience_benchmark import (
            FrontendMemoryLifecycleBenchmarkWorkspaceQuery,
            build_frontend_memory_lifecycle_benchmark_workspace_result,
        )

        validated = self._validate(req, FrontendMemoryLifecycleBenchmarkWorkspaceQuery)
        if isinstance(validated, AppResponse):
            return validated

        response = new_response(req)
        response.status = AppStatus.OK
        response.result = build_frontend_memory_lifecycle_benchmark_workspace_result(
            build_benchmark_workspace_payload(
                self._benchmark_artifact_root,
                project_root_resolver=_resolve_project_root,
            )
        ).model_dump(mode="json")
        return response

    def generate_memory_lifecycle_benchmark_slice(self, req: AppRequest) -> AppResponse:
        from mind.app.frontend_experience_benchmark import (
            FrontendMemoryLifecycleBenchmarkSliceGenerationRequest,
            build_frontend_memory_lifecycle_benchmark_slice_generation_result,
        )
        from mind.fixtures import (
            compile_public_dataset_local_slice,
            write_public_dataset_local_slice_json,
        )

        validated = self._validate(req, FrontendMemoryLifecycleBenchmarkSliceGenerationRequest)
        if isinstance(validated, AppResponse):
            return validated

        try:
            selector_kind, claim_ids, example_ids = resolve_dataset_selector_values(
                validated.dataset_name,
                validated.selector_values,
            )
            payload = compile_public_dataset_local_slice(
                validated.dataset_name,
                validated.raw_source_path,
                claim_ids=claim_ids,
                example_ids=example_ids,
                max_items=validated.max_items,
            )
            output_path = write_public_dataset_local_slice_json(validated.output_path, payload)
        except FileNotFoundError as exc:
            return self._error_response(req, AppErrorCode.NOT_FOUND, str(exc))
        except ValueError as exc:
            return self._error_response(req, AppErrorCode.VALIDATION_ERROR, str(exc))

        response = new_response(req)
        response.status = AppStatus.OK
        response.result = build_frontend_memory_lifecycle_benchmark_slice_generation_result(
            {
                "dataset_name": validated.dataset_name,
                "raw_source_path": validated.raw_source_path,
                "source_path": str(output_path),
                "bundle_count": len(coerce_list_payload(payload, "bundles")),
                "sequence_count": len(coerce_list_payload(payload, "sequence_specs")),
                "selector_kind": selector_kind,
                "selector_values": validated.selector_values,
                "max_items": validated.max_items,
            }
        ).model_dump(mode="json")
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

    def _error_response(self, req: AppRequest, code: AppErrorCode, message: str) -> AppResponse:
        response = new_response(req)
        response.status = AppStatus.ERROR
        response.error = AppError(code=code, message=message)
        return response
