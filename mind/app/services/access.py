"""Memory access application service."""

from __future__ import annotations

from typing import Any

from mind.access.service import AccessService
from mind.app._service_utils import latest_trace_ref, new_response
from mind.app.context import resolve_execution_context
from mind.app.contracts import AppRequest, AppResponse, AppStatus
from mind.app.errors import map_domain_error


class MemoryAccessService:
    """Provide runtime access to memories via AccessService.

    Methods: ``ask``, ``run_access``, ``explain_access``.
    """

    def __init__(self, access_service: AccessService) -> None:
        self._access = access_service

    def ask(self, req: AppRequest) -> AppResponse:
        """Ask a question against stored memories (auto mode)."""
        return self._do_run(req, mode="auto")

    def run_access(self, req: AppRequest) -> AppResponse:
        """Run access with an explicit mode."""
        mode = req.input.get("mode", "auto")
        return self._do_run(req, mode=mode)

    def explain_access(self, req: AppRequest) -> AppResponse:
        """Run access and return detailed trace explanation."""
        resp = self._do_run(req, mode=req.input.get("mode", "auto"))
        # The trace_ref is already set by _do_run; the full trace
        # is in the result payload under "trace" if present.
        return resp

    # ------------------------------------------------------------------

    def _do_run(self, req: AppRequest, *, mode: str) -> AppResponse:
        resp = new_response(req)
        ctx = resolve_execution_context(req.principal, req.session, req.policy)

        query = req.input.get("query", "")
        task_id = req.input.get("task_id", req.request_id)
        query_modes = req.input.get("query_modes", ["keyword"])
        filters = dict(req.input.get("filters", {}))
        episode_id = req.input.get("episode_id")
        if episode_id is not None:
            filters.setdefault("episode_id", episode_id)

        access_req: dict[str, Any] = {
            "query": query,
            "task_id": task_id,
            "query_modes": query_modes,
            "requested_mode": mode,
        }
        if filters:
            access_req["filters"] = filters
        for field in ("task_family", "time_budget_ms", "hard_constraints"):
            if field in req.input:
                access_req[field] = req.input[field]

        try:
            result = self._access.run(access_req, ctx)
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)
            return resp

        resp.status = AppStatus.OK
        resp.result = result.model_dump(mode="json")
        resp.trace_ref = latest_trace_ref(self._access.store)

        return resp
