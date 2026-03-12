"""Lightweight HTTP client for the product REST API."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


class MindAPIClient:
    """Thin JSON client over the REST API surface used by the product CLI."""

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.api_key = api_key

    def remember(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json("POST", "v1/memories", payload=payload)

    def recall(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json("POST", "v1/memories:recall", payload=payload)

    def ask(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json("POST", "v1/access:ask", payload=payload)

    def list_memories(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request_json("GET", "v1/memories", params=params)

    def open_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json("POST", "v1/sessions", payload=payload)

    def list_sessions(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request_json("GET", "v1/sessions", params=params)

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"v1/sessions/{session_id}")

    def health(self) -> dict[str, Any]:
        return self._request_json("GET", "v1/system/health")

    def readiness(self) -> dict[str, Any]:
        return self._request_json("GET", "v1/system/readiness")

    def config_summary(self) -> dict[str, Any]:
        return self._request_json("GET", "v1/system/config")

    def provider_status(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if payload:
            return self._request_json(
                "POST",
                "v1/system/provider-status:resolve",
                payload=payload,
            )
        return self._request_json("GET", "v1/system/provider-status")

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = urljoin(self.base_url, path)
        if params:
            encoded_params = urlencode(
                {key: value for key, value in params.items() if value is not None},
                doseq=True,
            )
            if encoded_params:
                separator = "&" if "?" in url else "?"
                url = f"{url}{separator}{encoded_params}"

        body: bytes | None = None
        headers = {
            "Accept": "application/json",
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url=url, data=body, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            response_body = exc.read().decode("utf-8")
            if response_body:
                return json.loads(response_body)
            raise RuntimeError(f"API request failed with HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"Unable to reach MIND API at {url}") from exc
