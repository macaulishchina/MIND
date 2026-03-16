"""Feedback application service (Phase α-1)."""

from __future__ import annotations

import logging
from typing import Any

from mind.app._service_utils import latest_trace_ref, new_response, result_status
from mind.app.context import resolve_execution_context
from mind.app.contracts import AppError, AppErrorCode, AppRequest, AppResponse, AppStatus
from mind.app.errors import map_domain_error
from mind.primitives.contracts import PrimitiveName, PrimitiveOutcome
from mind.primitives.service import PrimitiveService

_log = logging.getLogger(__name__)


class FeedbackService:
    """Record post-query feedback via the record_feedback primitive.

    Wraps ``PrimitiveService.record_feedback()`` with the standard app-layer
    request / response envelope.
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

    def record_feedback(self, req: AppRequest) -> AppResponse:
        """Record feedback for a previous access run."""
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

        feedback_req: dict[str, Any] = {
            "task_id": req.input.get("task_id", ""),
            "episode_id": req.input.get("episode_id", ""),
            "query": req.input.get("query", ""),
            "used_object_ids": req.input.get("used_object_ids", []),
            "helpful_object_ids": req.input.get("helpful_object_ids", []),
            "unhelpful_object_ids": req.input.get("unhelpful_object_ids", []),
            "quality_signal": req.input.get("quality_signal", 0.0),
            "cost": req.input.get("cost", 0.0),
        }

        try:
            result = self._primitive.record_feedback(feedback_req, ctx)
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)
            return resp

        if result.outcome is PrimitiveOutcome.SUCCESS and result.response is not None:
            resp.status = AppStatus.OK
            resp.result = {
                "feedback_object_id": result.response.get("feedback_object_id"),
            }
            resp.trace_ref = latest_trace_ref(
                self._primitive.store,
                primitive=PrimitiveName.RECORD_FEEDBACK,
            )
            # α-3.3: auto-enqueue PROMOTE_SCHEMA when positive feedback is high
            self._try_schedule_feedback(result.response, feedback_req)
        else:
            resp.status = result_status(result.outcome)
            resp.error = AppError(
                code=AppErrorCode.INTERNAL_ERROR,
                message=(
                    result.error.message
                    if result.error is not None
                    else "feedback recording failed"
                ),
            )
        return resp

    # ------------------------------------------------------------------
    # Scheduler integration

    def _try_schedule_feedback(
        self,
        response: dict[str, Any],
        feedback_req: dict[str, Any],
    ) -> None:
        """Best-effort call to scheduler.on_feedback_recorded.

        Queries the store for the real accumulated ``feedback_positive_count``
        on each helpful object so the scheduler threshold works correctly.
        """
        if self._scheduler is None:
            return
        try:
            store = self._primitive.store
            helpful = feedback_req.get("helpful_object_ids", [])
            for oid in helpful:
                # Read the target object to get its true positive count.
                try:
                    obj = store.read_object(oid)
                    count = int(obj.get("metadata", {}).get("feedback_positive_count", 0))
                except Exception:
                    count = 1
                self._scheduler.on_feedback_recorded(
                    feedback_object=response,
                    object_id=oid,
                    positive_feedback_count=count,
                )
        except Exception:
            _log.warning("scheduler.on_feedback_recorded failed", exc_info=True)
