"""Frontend LLM service CRUD and runtime state helpers (extracted from frontend_settings)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from mind.app.frontend_settings import (
    _FRONTEND_LLM_STATE_PREFERENCE_KEY,
    _FRONTEND_RUNTIME_STATE_PREFERENCE_KEY,
    _LLM_PROVIDER_CATALOG,
    FrontendLlmServiceActivateRequest,
    FrontendLlmServiceDeleteRequest,
    FrontendLlmServiceUpsertRequest,
    FrontendPersistedRuntimeState,
    FrontendSettingsUpdateRequest,
)


def load_frontend_llm_state(
    preferences: Mapping[str, Any] | None,
) -> dict[str, Any]:
    raw_state = (
        preferences.get(_FRONTEND_LLM_STATE_PREFERENCE_KEY)
        if isinstance(preferences, Mapping)
        else None
    )
    raw_state = raw_state if isinstance(raw_state, Mapping) else {}
    services = _load_llm_services(raw_state)
    active_service_id = str(raw_state.get("active_service_id") or "") or None
    if active_service_id not in {service["service_id"] for service in services}:
        active_service_id = None
    selected_service_id = str(raw_state.get("selected_service_id") or "") or None
    if selected_service_id not in {service["service_id"] for service in services}:
        selected_service_id = active_service_id or (services[0]["service_id"] if services else None)
    return {
        "selected_service_id": selected_service_id,
        "active_service_id": active_service_id,
        "services": services,
    }


def dump_frontend_llm_state(
    llm_state: Mapping[str, Any],
) -> dict[str, Any]:
    resolved = load_frontend_llm_state({_FRONTEND_LLM_STATE_PREFERENCE_KEY: llm_state})
    return {
        _FRONTEND_LLM_STATE_PREFERENCE_KEY: resolved,
    }


def apply_frontend_llm_state_update(
    llm_state: Mapping[str, Any] | None,
    update_request: FrontendSettingsUpdateRequest | Mapping[str, Any],
) -> dict[str, Any]:
    request = (
        update_request
        if isinstance(update_request, FrontendSettingsUpdateRequest)
        else FrontendSettingsUpdateRequest.model_validate(update_request)
    )
    resolved = load_frontend_llm_state({_FRONTEND_LLM_STATE_PREFERENCE_KEY: llm_state})
    service = find_frontend_llm_service(
        resolved,
        service_id=request.service_id,
        protocol=request.provider,
    )
    if service is None:
        if request.provider in {"stub", "deterministic"}:
            resolved["active_service_id"] = None
            return resolved
        if request.provider not in _LLM_PROVIDER_CATALOG:
            return resolved
        auto_service = {
            "service_id": f"managed-{request.provider}",
            "protocol": request.provider,
            "name": _default_llm_name(request.provider),
            "icon": _default_llm_icon(request.provider),
            "endpoint": _resolve_llm_provider_endpoint(request.provider, request.endpoint),
            "api_key": request.api_key.strip()
            if request.api_key and request.api_key.strip()
            else None,
            "active_model": request.model.strip()
            if request.model and request.model.strip()
            else None,
            "model_options": [request.model.strip()]
            if request.model and request.model.strip()
            else [],
        }
        resolved["services"] = [
            service_item
            for service_item in resolved["services"]
            if service_item["service_id"] != auto_service["service_id"]
        ] + [auto_service]
        resolved["selected_service_id"] = auto_service["service_id"]
        resolved["active_service_id"] = auto_service["service_id"]
        return resolved

    next_services: list[dict[str, Any]] = []
    for current in resolved["services"]:
        if current["service_id"] != service["service_id"]:
            next_services.append(dict(current))
            continue
        updated = dict(current)
        if request.model is not None:
            updated["active_model"] = request.model
            if request.model not in updated["model_options"]:
                updated["model_options"] = [request.model, *updated["model_options"]]
        if request.endpoint is not None:
            updated["endpoint"] = _resolve_llm_provider_endpoint(
                str(updated["protocol"]),
                request.endpoint,
            )
        if request.api_key is not None and request.api_key.strip():
            updated["api_key"] = request.api_key.strip()
        next_services.append(updated)
    resolved["services"] = next_services
    resolved["selected_service_id"] = service["service_id"]
    resolved["active_service_id"] = service["service_id"]
    return resolved

def frontend_llm_provider_catalog() -> dict[str, dict[str, Any]]:
    return {
        provider: {
            **meta,
            "models": list(meta["models"]),
        }
        for provider, meta in _LLM_PROVIDER_CATALOG.items()
    }


def provider_secret_env(provider: str) -> str | None:
    provider_meta = _LLM_PROVIDER_CATALOG.get(provider)
    if provider_meta is None:
        return None
    return str(provider_meta["secret_env"])

def find_frontend_llm_service(
    llm_state: Mapping[str, Any] | None,
    *,
    service_id: str | None = None,
    protocol: str | None = None,
) -> dict[str, Any] | None:
    resolved = load_frontend_llm_state({_FRONTEND_LLM_STATE_PREFERENCE_KEY: llm_state})
    if service_id is not None:
        for service in resolved["services"]:
            if service["service_id"] == service_id:
                return dict(service)
        return None
    if protocol is not None:
        active_service_id = resolved.get("active_service_id")
        if active_service_id is not None:
            for service in resolved["services"]:
                if service["service_id"] == active_service_id and service["protocol"] == protocol:
                    return dict(service)
        for service in resolved["services"]:
            if service["protocol"] == protocol:
                return dict(service)
    return None


def upsert_frontend_llm_service(
    llm_state: Mapping[str, Any] | None,
    request_payload: FrontendLlmServiceUpsertRequest | Mapping[str, Any],
    *,
    new_service_id: str,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    request = (
        request_payload
        if isinstance(request_payload, FrontendLlmServiceUpsertRequest)
        else FrontendLlmServiceUpsertRequest.model_validate(request_payload)
    )
    resolved = load_frontend_llm_state({_FRONTEND_LLM_STATE_PREFERENCE_KEY: llm_state})
    existing = (
        find_frontend_llm_service(resolved, service_id=request.service_id)
        if request.service_id
        else None
    )
    service_id = request.service_id or f"svc-{new_service_id}"
    protocol = request.protocol
    service = {
        "service_id": service_id,
        "protocol": protocol,
        "name": (request.name or "").strip() or _default_llm_name(protocol),
        "icon": (request.icon or "").strip() or None,
        "endpoint": _resolve_llm_provider_endpoint(protocol, request.endpoint),
        "api_key": (
            request.api_key.strip()
            if isinstance(request.api_key, str) and request.api_key.strip()
            else (existing.get("api_key") if existing is not None else None)
        ),
        "active_model": (
            request.model.strip()
            if isinstance(request.model, str) and request.model.strip()
            else (existing.get("active_model") if existing is not None else None)
        ),
        "model_options": list(existing.get("model_options", [])) if existing is not None else [],
    }
    model_options = service["model_options"]
    assert isinstance(model_options, list)
    if service["active_model"] and service["active_model"] not in model_options:
        service["model_options"] = [service["active_model"], *model_options]
    next_services: list[dict[str, Any]] = []
    replaced = False
    for current in resolved["services"]:
        if current["service_id"] != service_id:
            next_services.append(dict(current))
            continue
        next_services.append(service)
        replaced = True
    if not replaced:
        next_services.append(service)
    resolved["services"] = next_services
    resolved["selected_service_id"] = service_id
    if resolved.get("active_service_id") == service_id and service["active_model"] is None:
        resolved["active_service_id"] = None
    return resolved, service, "updated" if replaced else "created"


def remember_frontend_llm_models(
    llm_state: Mapping[str, Any] | None,
    *,
    service_id: str,
    models: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = load_frontend_llm_state({_FRONTEND_LLM_STATE_PREFERENCE_KEY: llm_state})
    unique_models = _dedupe_strings(models)
    if not unique_models:
        raise RuntimeError("no models were returned by the provider")
    next_services: list[dict[str, Any]] = []
    remembered: dict[str, Any] | None = None
    for current in resolved["services"]:
        if current["service_id"] != service_id:
            next_services.append(dict(current))
            continue
        updated = dict(current)
        updated["model_options"] = unique_models
        if updated.get("active_model") not in unique_models:
            updated["active_model"] = unique_models[0]
        remembered = updated
        next_services.append(updated)
    if remembered is None:
        raise RuntimeError("requested llm service was not found")
    resolved["services"] = next_services
    resolved["selected_service_id"] = service_id
    return resolved, remembered


def activate_frontend_llm_service(
    llm_state: Mapping[str, Any] | None,
    request_payload: FrontendLlmServiceActivateRequest | Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    request = (
        request_payload
        if isinstance(request_payload, FrontendLlmServiceActivateRequest)
        else FrontendLlmServiceActivateRequest.model_validate(request_payload)
    )
    resolved = load_frontend_llm_state({_FRONTEND_LLM_STATE_PREFERENCE_KEY: llm_state})
    next_services: list[dict[str, Any]] = []
    activated: dict[str, Any] | None = None
    for current in resolved["services"]:
        updated = dict(current)
        if current["service_id"] == request.service_id:
            selected_model = (
                request.model
                or updated.get("active_model")
                or (updated["model_options"][0] if updated["model_options"] else None)
            )
            if not selected_model:
                raise RuntimeError("请先拉取模型列表，再启用这个服务。")
            if updated["model_options"] and selected_model not in updated["model_options"]:
                raise RuntimeError("当前服务没有这个模型，请先刷新模型列表。")
            updated["active_model"] = selected_model
            activated = updated
        next_services.append(updated)
    if activated is None:
        raise RuntimeError("requested llm service was not found")
    resolved["services"] = next_services
    resolved["selected_service_id"] = activated["service_id"]
    resolved["active_service_id"] = activated["service_id"]
    return resolved, activated


def delete_frontend_llm_service(
    llm_state: Mapping[str, Any] | None,
    request_payload: FrontendLlmServiceDeleteRequest | Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    request = (
        request_payload
        if isinstance(request_payload, FrontendLlmServiceDeleteRequest)
        else FrontendLlmServiceDeleteRequest.model_validate(request_payload)
    )
    resolved = load_frontend_llm_state({_FRONTEND_LLM_STATE_PREFERENCE_KEY: llm_state})
    deleted = find_frontend_llm_service(resolved, service_id=request.service_id)
    if deleted is None:
        raise RuntimeError("requested llm service was not found")

    next_services = [
        dict(current)
        for current in resolved["services"]
        if current["service_id"] != request.service_id
    ]
    deleted_was_active = resolved.get("active_service_id") == request.service_id
    resolved["services"] = next_services
    if deleted_was_active:
        resolved["active_service_id"] = None

    remaining_ids = {service["service_id"] for service in next_services}
    if resolved.get("selected_service_id") not in remaining_ids:
        resolved["selected_service_id"] = resolved.get("active_service_id") or (
            next_services[0]["service_id"] if next_services else None
        )
    return resolved, deleted, deleted_was_active


def discover_frontend_llm_models(
    service: Mapping[str, Any],
) -> list[str]:
    protocol = str(service["protocol"])
    api_key = str(service.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("请先为这个服务填写 API Key。")
    request_endpoint = _llm_models_endpoint(protocol, str(service["endpoint"]))
    headers = _llm_model_headers(protocol, api_key)
    request = Request(request_endpoint, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=10.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"拉取模型列表失败（HTTP {exc.code}）。") from exc
    except URLError as exc:
        raise RuntimeError("当前无法连接到模型服务。") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("模型服务返回了无法识别的内容。") from exc
    models = _parse_llm_models(protocol, payload)
    if not models:
        raise RuntimeError("当前服务没有返回可用模型。")
    return models


def load_frontend_runtime_state(
    preferences: Mapping[str, Any] | None,
) -> FrontendPersistedRuntimeState | None:
    raw_state = (
        preferences.get(_FRONTEND_RUNTIME_STATE_PREFERENCE_KEY)
        if isinstance(preferences, Mapping)
        else None
    )
    if not isinstance(raw_state, Mapping):
        return None
    try:
        return FrontendPersistedRuntimeState.model_validate(raw_state)
    except Exception:
        return None


def dump_frontend_runtime_state(
    runtime_state: FrontendPersistedRuntimeState | Mapping[str, Any],
) -> dict[str, Any]:
    resolved = (
        runtime_state
        if isinstance(runtime_state, FrontendPersistedRuntimeState)
        else FrontendPersistedRuntimeState.model_validate(runtime_state)
    )
    return {_FRONTEND_RUNTIME_STATE_PREFERENCE_KEY: resolved.model_dump(mode="json")}


def _load_llm_services(raw_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_services = raw_state.get("services")
    if isinstance(raw_services, list):
        services = [
            normalized
            for item in raw_services
            if isinstance(item, Mapping)
            for normalized in [_normalize_llm_service(item)]
            if normalized is not None
        ]
        if services:
            return services
    return _migrate_legacy_llm_services(raw_state)


def _normalize_llm_service(raw_service: Mapping[str, Any]) -> dict[str, Any] | None:
    protocol = str(raw_service.get("protocol") or raw_service.get("provider") or "").strip()
    if protocol not in _LLM_PROVIDER_CATALOG:
        return None
    service_id = str(raw_service.get("service_id") or raw_service.get("id") or "").strip()
    if not service_id:
        return None
    active_model = (
        str(raw_service.get("active_model") or raw_service.get("model") or "").strip() or None
    )
    model_options = _dedupe_strings(
        raw_service.get("model_options") or raw_service.get("models") or []
    )
    if active_model and active_model not in model_options:
        model_options = [active_model, *model_options]
    api_key = raw_service.get("api_key")
    return {
        "service_id": service_id,
        "protocol": protocol,
        "name": str(raw_service.get("name") or _default_llm_name(protocol)).strip(),
        "icon": str(raw_service.get("icon")).strip() or None
        if raw_service.get("icon") is not None
        else None,
        "endpoint": _resolve_llm_provider_endpoint(protocol, raw_service.get("endpoint")),
        "api_key": api_key if isinstance(api_key, str) and api_key else None,
        "active_model": active_model,
        "model_options": model_options,
    }


def _migrate_legacy_llm_services(raw_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_providers = raw_state.get("providers")
    if not isinstance(raw_providers, Mapping):
        return []
    selected_provider = str(raw_state.get("selected_provider") or "").strip()
    services: list[dict[str, Any]] = []
    for provider_name, raw_provider in raw_providers.items():
        if provider_name not in _LLM_PROVIDER_CATALOG or not isinstance(raw_provider, Mapping):
            continue
        api_key = raw_provider.get("api_key")
        endpoint = raw_provider.get("endpoint")
        model = str(raw_provider.get("model") or "").strip()
        has_saved_values = bool(api_key) or endpoint not in (None, "") or bool(model)
        if not has_saved_values and provider_name != selected_provider:
            continue
        model_options = _dedupe_strings(
            [model, *_LLM_PROVIDER_CATALOG[provider_name]["models"]]
            if model
            else _LLM_PROVIDER_CATALOG[provider_name]["models"]
        )
        services.append(
            {
                "service_id": f"legacy-{provider_name}",
                "protocol": provider_name,
                "name": _default_llm_name(provider_name),
                "icon": _default_llm_icon(provider_name),
                "endpoint": _resolve_llm_provider_endpoint(provider_name, endpoint),
                "api_key": api_key if isinstance(api_key, str) and api_key else None,
                "active_model": model or (model_options[0] if model_options else None),
                "model_options": model_options,
            }
        )
    return services


def _resolve_runtime_service_id(
    llm_state: Mapping[str, Any],
    protocol: str | None,
    endpoint: str | None,
) -> str | None:
    if protocol is None:
        return None
    active_service_id = llm_state.get("active_service_id")
    for service in llm_state.get("services", []):
        if (
            service["service_id"] == active_service_id
            and service["protocol"] == protocol
            and _service_matches_runtime_endpoint(service, endpoint)
        ):
            return service["service_id"]
    if endpoint is not None:
        for service in llm_state.get("services", []):
            if service["protocol"] == protocol and _service_matches_runtime_endpoint(
                service, endpoint
            ):
                return service["service_id"]
    for service in llm_state.get("services", []):
        if service["protocol"] == protocol:
            return service["service_id"]
    return None


def _dedupe_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    deduped: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _default_llm_name(protocol: str) -> str:
    return str(_LLM_PROVIDER_CATALOG[protocol]["default_name"])


def _default_llm_icon(protocol: str) -> str:
    return str(_LLM_PROVIDER_CATALOG[protocol]["default_icon"])


def _default_llm_endpoint(protocol: str) -> str:
    return str(_LLM_PROVIDER_CATALOG[protocol]["default_endpoint"])


def _resolve_llm_provider_endpoint(provider: str, stored_endpoint: Any) -> str:
    base = str(stored_endpoint).strip() if isinstance(stored_endpoint, str) else ""
    if not base:
        return _default_llm_endpoint(provider)
    parts = urlsplit(base)
    if not parts.scheme or not parts.netloc:
        return _default_llm_endpoint(provider)
    path = _strip_llm_endpoint_suffix(provider, parts.path.rstrip("/"))
    official_parts = urlsplit(_default_llm_endpoint(provider))
    if not path and parts.netloc == official_parts.netloc:
        path = official_parts.path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def resolve_frontend_llm_runtime_endpoint(provider: str, stored_endpoint: Any) -> str:
    if provider not in _LLM_PROVIDER_CATALOG:
        return str(stored_endpoint).strip() if isinstance(stored_endpoint, str) else ""
    base = _resolve_llm_provider_endpoint(provider, stored_endpoint)
    parts = urlsplit(base)
    path = parts.path.rstrip("/")
    if provider == "openai":
        next_path = f"{path}/chat/completions" if path else "/chat/completions"
    elif provider == "claude":
        next_path = f"{path}/messages" if path else "/v1/messages"
    else:
        next_path = f"{path}/models" if path else "/v1beta/models"
    return urlunsplit((parts.scheme, parts.netloc, next_path, "", ""))


def _llm_models_endpoint(protocol: str, endpoint: str) -> str:
    parts = urlsplit(_resolve_llm_provider_endpoint(protocol, endpoint))
    path = parts.path.rstrip("/")
    if protocol == "openai":
        if path.endswith("/models"):
            next_path = path
        elif path.endswith("/v1"):
            next_path = f"{path}/models"
        elif not path:
            next_path = "/v1/models"
        else:
            next_path = f"{path}/models"
        return urlunsplit((parts.scheme, parts.netloc, next_path, "", ""))
    if protocol == "claude":
        if path.endswith("/models"):
            next_path = path
        elif path.endswith("/v1"):
            next_path = f"{path}/models"
        elif not path:
            next_path = "/v1/models"
        else:
            next_path = f"{path}/models"
        return urlunsplit((parts.scheme, parts.netloc, next_path, "", ""))
    if path.endswith("/models"):
        next_path = path
    elif not path:
        next_path = "/v1beta/models"
    else:
        next_path = f"{path}/models"
    return urlunsplit((parts.scheme, parts.netloc, next_path, "", ""))


def _strip_llm_endpoint_suffix(provider: str, path: str) -> str:
    if provider == "openai":
        for suffix in ("/responses", "/chat/completions", "/completions", "/models"):
            if path.endswith(suffix):
                return path[: -len(suffix)]
        return path
    if provider == "claude":
        for suffix in ("/messages", "/models"):
            if path.endswith(suffix):
                return path[: -len(suffix)]
        return path
    cleaned_path = path
    if ":generateContent" in cleaned_path:
        cleaned_path = cleaned_path.split(":generateContent", 1)[0]
    if "/models/" in cleaned_path:
        return cleaned_path.split("/models/", 1)[0]
    if cleaned_path.endswith("/models"):
        return cleaned_path[: -len("/models")]
    return cleaned_path


def _service_matches_runtime_endpoint(
    service: Mapping[str, Any], runtime_endpoint: str | None
) -> bool:
    if runtime_endpoint is None:
        return False
    return resolve_frontend_llm_runtime_endpoint(
        str(service["protocol"]),
        str(service["endpoint"]),
    ) == str(runtime_endpoint)


def _llm_model_headers(protocol: str, api_key: str) -> dict[str, str]:
    if protocol == "openai":
        return {"Authorization": f"Bearer {api_key}"}
    if protocol == "claude":
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    return {"x-goog-api-key": api_key}


def _parse_llm_models(protocol: str, payload: Mapping[str, Any]) -> list[str]:
    if protocol in {"openai", "claude"}:
        models = []
        for item in payload.get("data", []):
            if not isinstance(item, Mapping):
                continue
            model_id = str(item.get("id") or item.get("name") or "").strip()
            if model_id and model_id not in models:
                models.append(model_id)
        return models
    models = []
    for item in payload.get("models", []):
        if not isinstance(item, Mapping):
            continue
        raw_name = str(item.get("name") or item.get("baseModelId") or "").strip()
        model_id = raw_name.split("/")[-1] if "/" in raw_name else raw_name
        if model_id and model_id not in models:
            models.append(model_id)
    return models


