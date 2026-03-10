"""Memory ingest application service."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from mind.app._service_utils import latest_trace_ref, new_response, result_error, result_status
from mind.app.context import resolve_execution_context
from mind.app.contracts import AppRequest, AppResponse, AppStatus
from mind.app.errors import map_domain_error
from mind.primitives.contracts import PrimitiveName, PrimitiveOutcome
from mind.primitives.service import PrimitiveService


class MemoryIngestService:
    """Ingest memories via write_raw primitive.

    Methods: ``remember``, ``import_raw``, ``append_turn``.
    """

    def __init__(self, primitive_service: PrimitiveService) -> None:
        self._primitive = primitive_service

    def remember(self, req: AppRequest) -> AppResponse:
        """Store a memory from user input."""
        return self._do_write(req, record_kind="user_message")

    def import_raw(self, req: AppRequest) -> AppResponse:
        """Import a raw record."""
        record_kind = req.input.get("record_kind", "user_message")
        return self._do_write(req, record_kind=record_kind)

    def append_turn(self, req: AppRequest) -> AppResponse:
        """Append a conversation turn."""
        return self._do_write(req, record_kind="user_message")

    # ------------------------------------------------------------------

    def _do_write(self, req: AppRequest, *, record_kind: str) -> AppResponse:
        resp = new_response(req)
        ctx = resolve_execution_context(req.principal, req.session, req.policy)

        write_req: dict[str, Any] = {
            "record_kind": req.input.get("record_kind", record_kind),
            "content": req.input.get("content", ""),
            "episode_id": req.input.get("episode_id", f"ep-{uuid4().hex[:8]}"),
            "timestamp_order": req.input.get("timestamp_order", 1),
        }

        # Optional provenance
        if req.input.get("direct_provenance"):
            write_req["direct_provenance"] = req.input["direct_provenance"]

        try:
            result = self._primitive.write_raw(write_req, ctx)
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)
            return resp

        if result.outcome is PrimitiveOutcome.SUCCESS and result.response is not None:
            resp.status = AppStatus.OK
            resp.result = {
                "object_id": result.response.get("object_id"),
                "version": result.response.get("version"),
                "provenance_id": result.response.get("provenance_id"),
            }
            resp.trace_ref = latest_trace_ref(
                self._primitive.store,
                primitive=PrimitiveName.WRITE_RAW,
            )
        else:
            resp.status = result_status(result.outcome)
            resp.error = result_error(result)
            resp.trace_ref = latest_trace_ref(
                self._primitive.store,
                primitive=PrimitiveName.WRITE_RAW,
            )

        return resp
