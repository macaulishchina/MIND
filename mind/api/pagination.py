"""REST pagination helpers."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic pagination envelope for list payloads."""

    items: list[T] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


def parse_pagination(limit: int = 50, offset: int = 0) -> tuple[int, int]:
    """Normalize pagination inputs to safe bounds."""

    normalized_limit = min(max(limit, 1), 100)
    normalized_offset = max(offset, 0)
    return normalized_limit, normalized_offset
