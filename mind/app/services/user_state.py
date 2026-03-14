"""User state application service with optional persistent store backing."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from mind.access import AccessMode
from mind.app._service_utils import new_response
from mind.app.contracts import AppError, AppErrorCode, AppRequest, AppResponse, AppStatus
from mind.app.errors import map_domain_error
from mind.kernel.store import StoreError, UserStateStore

_DEFAULT_RUNTIME_DEFAULTS: dict[str, Any] = {
    "default_access_mode": AccessMode.AUTO.value,
    "budget_limit": None,
    "retention_class": "standard",
    "dev_mode": False,
    "conceal_visibility": False,
    "fallback_policy": "reject",
}


class UserStateService:
    """Manages principal, session, and preferences lifecycle."""

    def __init__(self, store: Any = None) -> None:
        self._store = store
        self._principals: dict[str, dict[str, Any]] = {}
        self._sessions: dict[str, dict[str, Any]] = {}

    def resolve_principal(self, req: AppRequest) -> AppResponse:
        """Resolve or create a principal identity."""
        resp = new_response(req)
        principal_payload = _principal_payload(req)
        principal_id = str(principal_payload["principal_id"])

        store = self._user_state_store()
        if store is None:
            self._principals.setdefault(principal_id, principal_payload)
            resp.status = AppStatus.OK
            resp.result = self._principals[principal_id]
            return resp

        try:
            existing = store.read_principal(principal_id)
        except StoreError:
            existing = None
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)
            return resp

        if existing is None:
            try:
                resp.result = store.insert_principal(principal_payload)
            except Exception as exc:
                resp.status = AppStatus.ERROR
                resp.error = map_domain_error(exc)
                return resp
        else:
            resp.result = existing

        resp.status = AppStatus.OK
        return resp

    def get_principal(self, req: AppRequest) -> AppResponse:
        """Get an existing principal identity."""
        resp = new_response(req)
        principal_id = str(
            req.input.get(
                "principal_id",
                req.principal.principal_id if req.principal is not None else "",
            )
        )
        if not principal_id:
            resp.status = AppStatus.ERROR
            resp.error = AppError(
                code=AppErrorCode.VALIDATION_ERROR,
                message="principal_id required",
            )
            return resp

        store = self._user_state_store()
        if store is None:
            principal = self._principals.get(principal_id)
            if principal is None:
                resp.status = AppStatus.NOT_FOUND
                resp.error = AppError(
                    code=AppErrorCode.NOT_FOUND,
                    message=f"principal {principal_id} not found",
                )
                return resp
            resp.status = AppStatus.OK
            resp.result = principal
            return resp

        try:
            resp.result = store.read_principal(principal_id)
            resp.status = AppStatus.OK
        except StoreError:
            resp.status = AppStatus.NOT_FOUND
            resp.error = AppError(
                code=AppErrorCode.NOT_FOUND,
                message=f"principal {principal_id} not found",
            )
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)

        return resp

    def open_session(self, req: AppRequest) -> AppResponse:
        """Open a new session for a principal."""
        resp = new_response(req)
        try:
            session_payload = _session_payload(req)
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)
            return resp
        session_id = str(session_payload["session_id"])

        store = self._user_state_store()
        if store is None:
            self._sessions[session_id] = session_payload
            resp.status = AppStatus.OK
            resp.result = session_payload
            return resp

        try:
            self._ensure_principal(store, req, principal_id=str(session_payload["principal_id"]))
            try:
                current = store.read_session(session_id)
            except StoreError:
                current = None

            if current is None:
                resp.result = store.insert_session(session_payload)
            else:
                resp.result = store.update_session(
                    session_id,
                    {
                        "conversation_id": session_payload["conversation_id"],
                        "channel": session_payload["channel"],
                        "client_id": session_payload["client_id"],
                        "device_id": session_payload["device_id"],
                        "metadata": session_payload["metadata"],
                    },
                )
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)
            return resp

        resp.status = AppStatus.OK
        return resp

    def get_session(self, req: AppRequest) -> AppResponse:
        """Get session details."""
        resp = new_response(req)
        session_id = str(req.input.get("session_id", ""))
        if not session_id:
            resp.status = AppStatus.ERROR
            resp.error = AppError(
                code=AppErrorCode.VALIDATION_ERROR,
                message="session_id required",
            )
            return resp

        store = self._user_state_store()
        if store is None:
            if session_id in self._sessions:
                resp.status = AppStatus.OK
                resp.result = self._sessions[session_id]
            else:
                resp.status = AppStatus.NOT_FOUND
                resp.error = AppError(
                    code=AppErrorCode.NOT_FOUND,
                    message=f"session {session_id} not found",
                )
            return resp

        try:
            resp.result = store.read_session(session_id)
            resp.status = AppStatus.OK
        except StoreError:
            resp.status = AppStatus.NOT_FOUND
            resp.error = AppError(
                code=AppErrorCode.NOT_FOUND,
                message=f"session {session_id} not found",
            )
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)

        return resp

    def list_sessions(self, req: AppRequest) -> AppResponse:
        """List sessions, optionally scoped to one principal."""
        resp = new_response(req)
        principal_id = req.input.get("principal_id")
        if principal_id is None and req.principal is not None:
            principal_id = req.principal.principal_id

        store = self._user_state_store()
        if store is None:
            sessions = list(self._sessions.values())
            if principal_id is not None:
                sessions = [
                    session
                    for session in sessions
                    if session.get("principal_id") == str(principal_id)
                ]
            resp.status = AppStatus.OK
            resp.result = {
                "sessions": sessions,
                "total": len(sessions),
            }
            return resp

        try:
            sessions = store.list_sessions(
                principal_id=str(principal_id) if principal_id is not None else None
            )
            resp.status = AppStatus.OK
            resp.result = {
                "sessions": sessions,
                "total": len(sessions),
            }
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)

        return resp

    def update_user_preferences(self, req: AppRequest) -> AppResponse:
        """Update user preferences for a principal."""
        resp = new_response(req)
        principal_id = str(
            req.input.get(
                "principal_id",
                req.principal.principal_id if req.principal is not None else "",
            )
        )
        if not principal_id:
            resp.status = AppStatus.ERROR
            resp.error = AppError(
                code=AppErrorCode.VALIDATION_ERROR,
                message="principal_id required",
            )
            return resp

        preferences = dict(req.input.get("preferences", {}))
        store = self._user_state_store()
        if store is None:
            if principal_id not in self._principals:
                resp.status = AppStatus.NOT_FOUND
                resp.error = AppError(
                    code=AppErrorCode.NOT_FOUND,
                    message=f"principal {principal_id} not found",
                )
                return resp
            self._principals[principal_id]["preferences"] = preferences
            resp.status = AppStatus.OK
            resp.result = self._principals[principal_id]
            return resp

        try:
            principal = store.read_principal(principal_id)
            merged = {
                **principal,
                "preferences": {
                    **dict(principal.get("preferences", {})),
                    **preferences,
                },
            }
            resp.result = store.insert_principal(merged)
            resp.status = AppStatus.OK
        except StoreError:
            resp.status = AppStatus.NOT_FOUND
            resp.error = AppError(
                code=AppErrorCode.NOT_FOUND,
                message=f"principal {principal_id} not found",
            )
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)

        return resp

    def get_runtime_defaults(self, req: AppRequest) -> AppResponse:
        """Get resolved execution defaults for a principal."""
        resp = new_response(req)

        resolved = dict(_DEFAULT_RUNTIME_DEFAULTS)
        principal_id = req.input.get("principal_id")
        if principal_id is None and req.principal is not None:
            principal_id = req.principal.principal_id

        store = self._user_state_store()
        if store is None:
            principal = self._principals.get(str(principal_id), {}) if principal_id else {}
            resolved.update(_runtime_defaults_from_preferences(principal.get("preferences", {})))
            resp.status = AppStatus.OK
            resp.result = resolved
            return resp

        try:
            if principal_id is not None:
                principal = store.read_principal(str(principal_id))
                resolved.update(
                    _runtime_defaults_from_preferences(principal.get("preferences", {}))
                )
            resp.status = AppStatus.OK
            resp.result = resolved
        except StoreError:
            resp.status = AppStatus.OK
            resp.result = resolved
        except Exception as exc:
            resp.status = AppStatus.ERROR
            resp.error = map_domain_error(exc)

        return resp

    def _user_state_store(self) -> UserStateStore | None:
        store = self._store
        if isinstance(store, UserStateStore):
            return store
        return None

    def _ensure_principal(
        self,
        store: UserStateStore,
        req: AppRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        try:
            return store.read_principal(principal_id)
        except StoreError:
            principal_payload = _principal_payload(req)
            principal_payload["principal_id"] = principal_id
            return store.insert_principal(principal_payload)


def _principal_payload(req: AppRequest) -> dict[str, Any]:
    principal_id = req.input.get(
        "principal_id",
        req.principal.principal_id if req.principal is not None else f"principal-{uuid4().hex[:8]}",
    )
    principal_kind = req.input.get(
        "principal_kind",
        req.principal.principal_kind if req.principal is not None else "user",
    )
    tenant_id = req.input.get(
        "tenant_id",
        req.principal.tenant_id if req.principal is not None else "default",
    )
    user_id = req.input.get(
        "user_id",
        req.principal.user_id if req.principal is not None else None,
    )
    roles = req.input.get("roles")
    if roles is None and req.principal is not None:
        roles = list(req.principal.roles)
    capabilities = req.input.get("capabilities")
    if capabilities is None and req.principal is not None:
        capabilities = [capability.value for capability in req.principal.capabilities]

    return {
        "principal_id": principal_id,
        "principal_kind": principal_kind,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "roles": roles or [],
        "capabilities": capabilities or ["memory_read"],
        "preferences": dict(req.input.get("preferences", {})),
    }


def _session_payload(req: AppRequest) -> dict[str, Any]:
    session_id = req.input.get(
        "session_id",
        req.session.session_id if req.session is not None else f"session-{uuid4().hex[:8]}",
    )
    principal_id = req.input.get(
        "principal_id",
        req.principal.principal_id if req.principal is not None else "",
    )
    if not principal_id:
        raise StoreError("principal_id required to open session")

    metadata = dict(req.input.get("metadata", {}))
    metadata.setdefault("request_id", req.request_id)
    if req.idempotency_key is not None:
        metadata.setdefault("idempotency_key", req.idempotency_key)

    return {
        "session_id": session_id,
        "principal_id": principal_id,
        "conversation_id": req.input.get(
            "conversation_id",
            req.session.conversation_id if req.session is not None else None,
        ),
        "channel": req.input.get(
            "channel",
            req.session.channel if req.session is not None else "internal",
        ),
        "client_id": req.input.get(
            "client_id",
            req.session.client_id if req.session is not None else None,
        ),
        "device_id": req.input.get(
            "device_id",
            req.session.device_id if req.session is not None else None,
        ),
        "metadata": metadata,
    }


def _runtime_defaults_from_preferences(preferences: dict[str, Any]) -> dict[str, Any]:
    return {key: preferences[key] for key in _DEFAULT_RUNTIME_DEFAULTS if key in preferences}
