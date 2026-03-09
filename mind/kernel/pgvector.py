"""Minimal SQLAlchemy vector type for pgvector-backed storage."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from .retrieval import vector_literal


class Vector(sa.types.UserDefinedType[tuple[float, ...]]):
    """Small custom VECTOR(n) type without an extra Python dependency."""

    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_: Any) -> str:
        return f"VECTOR({self.dimensions})"

    def bind_processor(self, dialect: sa.Dialect) -> Any:
        del dialect

        def process(value: tuple[float, ...] | None) -> str | None:
            if value is None:
                return None
            return vector_literal(value)

        return process

    def bind_expression(self, bindvalue: sa.BindParameter[tuple[float, ...]]) -> sa.Cast[Any]:
        return sa.cast(bindvalue, self)

    def result_processor(self, dialect: sa.Dialect, coltype: Any) -> Any:
        del dialect, coltype

        def process(value: Any) -> tuple[float, ...] | None:
            if value is None:
                return None
            if isinstance(value, str):
                stripped = value.strip().removeprefix("[").removesuffix("]")
                if not stripped:
                    return tuple()
                return tuple(float(part) for part in stripped.split(","))
            if isinstance(value, list | tuple):
                return tuple(float(part) for part in value)
            raise TypeError(f"unsupported pgvector value {value!r}")

        return process
