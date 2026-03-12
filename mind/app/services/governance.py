"""Governance application service."""

from __future__ import annotations

from typing import Any

from mind.app._service_utils import latest_audit_ref, new_response
from mind.app.context import resolve_execution_context
from mind.app.contracts import AppRequest, AppResponse, AppStatus
from mind.app.errors import map_domain_error
from mind.governance.service import GovernanceService


class GovernanceAppService:
    """Governance workflows via GovernanceService.

    Methods: ``plan_conceal``, ``preview_conceal``, ``execute_conceal``.
    """

    def __init__(self, governance_service: GovernanceService) -> None:
        self._governance = governance_service

    def plan_conceal(self, req: AppRequest) -> AppResponse:
        """Plan a concealment operation."""
        return self._call_governance(req, "plan_conceal")

    def preview_conceal(self, req: AppRequest) -> AppResponse:
        """Preview a concealment operation."""
        return self._call_governance(req, "preview_conceal")

    def execute_conceal(self, req: AppRequest) -> AppResponse:
        """Execute a concealment operation."""
        return self._call_governance(req, "execute_conceal")

    # ------------------------------------------------------------------

    def _call_governance(self, req: AppRequest, method: str) -> AppResponse:
        resp = new_response(req)
        ctx = resolve_execution_context(
            req.principal,
            req.session,
            req.policy,
            req.provider_selection,
        )
        payload = _governance_payload(method, req.input)

        try:
            func = getattr(self._governance, method)
            result = func(payload, ctx)
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)
            return resp

        resp.status = AppStatus.OK
        if hasattr(result, "model_dump"):
            resp.result = result.model_dump(mode="json")
        elif isinstance(result, dict):
            resp.result = result
        else:
            resp.result = {"raw": str(result)}

        operation_id = resp.result.get("operation_id") if resp.result is not None else None
        resp.audit_ref = latest_audit_ref(self._governance.store, operation_id=operation_id)
        if resp.audit_ref is not None:
            resp.trace_ref = resp.audit_ref

        return resp


def _governance_payload(method: str, raw_input: dict[str, Any]) -> dict[str, Any]:
    payload = dict(raw_input)
    if method != "plan_conceal" or "selector" in payload:
        return payload

    selector: dict[str, Any] = {}
    for key in (
        "object_ids",
        "provenance_ids",
        "producer_kind",
        "producer_id",
        "user_id",
        "model_id",
        "episode_id",
        "captured_after",
        "captured_before",
    ):
        if key in payload:
            selector[key] = payload.pop(key)

    object_id = payload.pop("object_id", None)
    if object_id is not None:
        selector["object_ids"] = [object_id]

    provenance_id = payload.pop("provenance_id", None)
    if provenance_id is not None:
        selector["provenance_ids"] = [provenance_id]

    return {
        "selector": selector,
        "reason": payload.get("reason", ""),
    }
