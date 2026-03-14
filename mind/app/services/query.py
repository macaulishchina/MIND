"""Memory query application service."""

from __future__ import annotations

from typing import Any

from mind.app._service_utils import latest_trace_ref, new_response, result_error, result_status
from mind.app.context import resolve_execution_context
from mind.app.contracts import AppError, AppErrorCode, AppRequest, AppResponse, AppStatus
from mind.app.errors import map_domain_error
from mind.kernel.schema import public_object_view
from mind.kernel.store import MemoryStore
from mind.primitives.contracts import PrimitiveErrorCode, PrimitiveName, PrimitiveOutcome
from mind.primitives.service import PrimitiveService


class MemoryQueryService:
    """Query memories via read/retrieve/iter primitives.

    Methods: ``get_memory``, ``list_memories``, ``recall``, ``search``.
    """

    def __init__(
        self,
        primitive_service: PrimitiveService,
        store: MemoryStore,
        *,
        request_defaults_resolver: Any = None,
    ) -> None:
        self._primitive = primitive_service
        self._store = store
        self._request_defaults_resolver = request_defaults_resolver

    def get_memory(self, req: AppRequest) -> AppResponse:
        """Get a single memory object by ID."""
        if self._request_defaults_resolver is not None:
            req = self._request_defaults_resolver(
                req,
                include_provider_selection=False,
                respect_request_policy=True,
            )
        resp = new_response(req)
        ctx = resolve_execution_context(
            req.principal,
            req.session,
            req.policy,
            req.provider_selection,
        )
        object_id = req.input.get("object_id", "")

        if not object_id:
            resp.status = AppStatus.ERROR
            resp.error = AppError(code=AppErrorCode.VALIDATION_ERROR, message="object_id required")
            return resp

        try:
            result = self._primitive.read({"object_ids": [object_id]}, ctx)
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)
            return resp

        if result.outcome is PrimitiveOutcome.SUCCESS and result.response is not None:
            objects = result.response.get("objects", [])
            if objects:
                resp.status = AppStatus.OK
                resp.result = {"object": objects[0]}
            else:
                resp.status = AppStatus.NOT_FOUND
                resp.error = AppError(
                    code=AppErrorCode.NOT_FOUND,
                    message=f"object {object_id} not found",
                )
        else:
            if (
                result.error is not None
                and result.error.code is PrimitiveErrorCode.OBJECT_NOT_FOUND
            ):
                resp.status = AppStatus.NOT_FOUND
                resp.error = AppError(
                    code=AppErrorCode.NOT_FOUND,
                    message=result.error.message,
                    retryable=result.error.retryable,
                    details=dict(result.error.details),
                )
            else:
                resp.status = result_status(result.outcome)
                resp.error = result_error(result)
        resp.trace_ref = latest_trace_ref(self._primitive.store, primitive=PrimitiveName.READ)
        return resp

    def list_memories(self, req: AppRequest) -> AppResponse:
        """List recent memory objects with optional filters."""
        if self._request_defaults_resolver is not None:
            req = self._request_defaults_resolver(
                req,
                include_provider_selection=False,
                respect_request_policy=True,
            )
        resp = new_response(req)

        try:
            object_types = req.input.get("object_types", ())
            statuses = req.input.get("statuses", ())
            episode_id = req.input.get("episode_id")
            task_id = req.input.get("task_id")
            limit = req.input.get("limit", 50)
            offset = req.input.get("offset", 0)

            all_objects = list(
                self._store.iter_latest_objects(
                    object_types=object_types,
                    statuses=statuses,
                    episode_id=episode_id,
                    task_id=task_id,
                )
            )
            sliced = all_objects[offset : offset + limit]
            resp.status = AppStatus.OK
            resp.result = {
                "objects": sliced,
                "total": len(all_objects),
                "limit": limit,
                "offset": offset,
            }
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)

        return resp

    def recall(self, req: AppRequest) -> AppResponse:
        """Recall memories via retrieve primitive."""
        if self._request_defaults_resolver is not None:
            req = self._request_defaults_resolver(
                req,
                include_provider_selection=False,
                respect_request_policy=True,
            )
        resp = new_response(req)
        ctx = resolve_execution_context(
            req.principal,
            req.session,
            req.policy,
            req.provider_selection,
        )

        query = req.input.get("query", "")
        query_modes = req.input.get("query_modes", ["keyword"])
        max_candidates = req.input.get("max_candidates", 10)
        filters: dict[str, Any] = req.input.get("filters", {})

        retrieve_req: dict[str, Any] = {
            "query": query,
            "query_modes": query_modes,
            "budget": {"max_candidates": max_candidates},
            "filters": filters,
        }

        try:
            result = self._primitive.retrieve(retrieve_req, ctx)
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)
            return resp

        if result.outcome is PrimitiveOutcome.SUCCESS and result.response is not None:
            resp.status = AppStatus.OK
            response_payload = dict(result.response)
            candidate_ids = list(response_payload.get("candidate_ids") or [])
            response_payload["candidates"] = self._candidate_summaries(candidate_ids)
            resp.result = response_payload
        else:
            resp.status = result_status(result.outcome)
            resp.error = result_error(result)
        resp.trace_ref = latest_trace_ref(self._primitive.store, primitive=PrimitiveName.RETRIEVE)
        return resp

    def search(self, req: AppRequest) -> AppResponse:
        """Search memories using store search."""
        if self._request_defaults_resolver is not None:
            req = self._request_defaults_resolver(
                req,
                include_provider_selection=False,
                respect_request_policy=True,
            )
        resp = new_response(req)

        try:
            query = req.input.get("query", "")
            max_candidates = req.input.get("max_candidates", 20)
            query_modes = req.input.get("query_modes", ["keyword"])
            object_types = req.input.get("object_types", ())
            statuses = req.input.get("statuses", ())
            episode_id = req.input.get("episode_id")
            task_id = req.input.get("task_id")

            matches = list(
                self._store.search_latest_objects(
                    query=query,
                    query_modes=query_modes,
                    max_candidates=max_candidates,
                    object_types=object_types,
                    statuses=statuses,
                    episode_id=episode_id,
                    task_id=task_id,
                )
            )
            resp.status = AppStatus.OK
            resp.result = {
                "matches": [{"object": m.object, "score": m.score} for m in matches],
                "total": len(matches),
            }
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)

        return resp

    def _candidate_summaries(self, candidate_ids: list[str]) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for object_id in candidate_ids:
            try:
                obj = public_object_view(self._store.read_object(object_id))
            except Exception:
                continue

            summary: dict[str, Any] = {
                "object_id": str(obj.get("id") or object_id),
                "object_type": str(obj.get("type") or "unknown"),
            }
            preview = _content_preview(obj.get("content"))
            if preview:
                summary["content_preview"] = preview
            summaries.append(summary)
        return summaries


def _content_preview(content: Any) -> str | None:
    if isinstance(content, str):
        compact = " ".join(content.split())
        return compact[:117] + "..." if len(compact) > 120 else compact
    return None
