"""Memory ingest application service."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from mind.app._service_utils import latest_trace_ref, new_response, result_error, result_status
from mind.app.context import resolve_execution_context
from mind.app.contracts import AppRequest, AppResponse, AppStatus
from mind.app.errors import map_domain_error
from mind.primitives.contracts import PrimitiveName, PrimitiveOutcome
from mind.primitives.service import PrimitiveService

_log = logging.getLogger(__name__)


class MemoryIngestService:
    """Ingest memories via write_raw primitive.

    Methods: ``remember``, ``import_raw``, ``append_turn``.
    """

    def __init__(
        self,
        primitive_service: PrimitiveService,
        *,
        request_defaults_resolver: Any = None,
        scheduler: Any | None = None,
    ) -> None:
        self._primitive = primitive_service
        self._request_defaults_resolver = request_defaults_resolver
        self._scheduler = scheduler

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
        raw_episode_id = req.input.get("episode_id")
        episode_id = (
            raw_episode_id
            if isinstance(raw_episode_id, str) and raw_episode_id.strip()
            else f"ep-{uuid4().hex[:8]}"
        )

        write_req: dict[str, Any] = {
            "record_kind": req.input.get("record_kind", record_kind),
            "content": req.input.get("content", ""),
            "episode_id": episode_id,
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
                "episode_id": episode_id,
            }
            resp.trace_ref = latest_trace_ref(
                self._primitive.store,
                primitive=PrimitiveName.WRITE_RAW,
            )
            # α-3.2: auto-enqueue REFLECT_EPISODE when a TaskEpisode is completed
            self._try_schedule_episode_completed(episode_id, result.response)
        else:
            resp.status = result_status(result.outcome)
            resp.error = result_error(result)
            resp.trace_ref = latest_trace_ref(
                self._primitive.store,
                primitive=PrimitiveName.WRITE_RAW,
            )

        return resp

    # ------------------------------------------------------------------
    # Scheduler integration

    def _try_schedule_episode_completed(
        self,
        episode_id: str,
        response: dict[str, Any],
    ) -> None:
        """Best-effort enqueue of REFLECT_EPISODE via the scheduler.

        The *response* dict is the write_raw primitive result (object_id, version,
        provenance_id).  We read the actual episode object from the store so the
        scheduler can inspect ``metadata.result`` to decide whether the episode is
        completed.
        """
        if self._scheduler is None:
            return
        try:
            # Try to read the TaskEpisode for this episode from the store so
            # the scheduler can check metadata.result.
            store = self._primitive.store
            episodes = store.iter_latest_objects(
                object_types=("TaskEpisode",),
                episode_id=episode_id,
            )
            if episodes:
                episode_obj = episodes[0]
            else:
                # Fallback: wrap write-raw response as best-effort episode stub.
                episode_obj = response
            self._scheduler.on_episode_completed(episode_id, episode_obj)
        except Exception:
            _log.warning("scheduler.on_episode_completed failed for %s", episode_id, exc_info=True)
