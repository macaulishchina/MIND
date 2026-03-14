"""REST authentication helpers."""

from __future__ import annotations

import hmac
from os import environ
from typing import Annotated

from fastapi import Header

from mind.app.context import Capability, PrincipalContext, PrincipalKind
from mind.app.errors import AuthorizationError

APIKeyHeader = Annotated[str | None, Header(alias="X-API-Key")]


async def require_api_key(x_api_key: APIKeyHeader = None) -> PrincipalContext:
    """Validate the API key header and return the authenticated principal."""

    expected = environ.get("MIND_API_KEY")
    if not expected:
        raise AuthorizationError("api key auth is not configured")
    if not hmac.compare_digest(x_api_key or "", expected):
        raise AuthorizationError("invalid api key")

    return PrincipalContext(
        principal_id="api-key",
        principal_kind=PrincipalKind.API_KEY,
        tenant_id="default",
        user_id="api-key",
        roles=["api"],
        capabilities=list(Capability),
    )
