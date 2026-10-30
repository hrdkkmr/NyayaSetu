"""Dialect-portable column types.

PostgreSQL is the production database (with pgvector). SQLite is supported for
local development and the automated test suite, so vector and JSON columns
degrade to portable representations there.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator, UserDefinedType


class GUID(TypeDecorator[uuid.UUID]):
    """UUID stored natively on PostgreSQL and as a 36-char string elsewhere."""

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        return value if dialect.name == "postgresql" else str(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> uuid.UUID | None:
        if value is None:
            return None
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class JSONType(TypeDecorator[Any]):
    """JSONB on PostgreSQL, JSON elsewhere."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.JSONB())
        return dialect.type_descriptor(JSON())


class _PgVector(UserDefinedType[list[float]]):
    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def get_col_spec(self, **_: Any) -> str:
        return f"vector({self.dim})"


class EmbeddingVector(TypeDecorator[list[float]]):
    """pgvector `vector(n)` on PostgreSQL, JSON-encoded text elsewhere."""

    impl = String
    cache_ok = True

    def __init__(self, dim: int) -> None:
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(String())

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        if dialect.name == "postgresql":
            return list(value)
        return json.dumps([round(float(x), 6) for x in value])

    def process_result_value(self, value: Any, dialect: Dialect) -> list[float] | None:
        if value is None:
            return None
        if isinstance(value, str):
            return [float(x) for x in json.loads(value)]
        return [float(x) for x in value]
