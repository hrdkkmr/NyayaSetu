from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401 - registers tables
from alembic import context
from app.config import get_settings
from app.db.base import Base

target_metadata = Base.metadata


def render_item(type_: str, obj: Any, autogen_context: Any) -> str | bool:
    if type_ == "type" and obj.__class__.__module__ == "app.db.types":
        autogen_context.imports.add("import app.db.types")
        args = f"{obj.dim}" if hasattr(obj, "dim") else ""
        return f"app.db.types.{obj.__class__.__name__}({args})"
    return False


def run_migrations_offline() -> None:
    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True,
                      render_item=render_item, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Any) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_item=render_item,
                      render_as_batch=connection.dialect.name == "sqlite", compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
