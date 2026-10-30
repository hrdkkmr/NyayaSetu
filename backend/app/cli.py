"""Operational commands.

    python -m app.cli ingest [--live] [--force]   ingest official legal sources
    python -m app.cli create-admin EMAIL NAME     create an admin (password read from stdin/prompt)
    python -m app.cli reminders                   run deadline reminders once
    python -m app.cli init-sqlite                 create tables on a local SQLite database (dev only)
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from app.config import get_settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.db.session import get_engine, session_scope
from app.models import User, UserPreferences
from app.models.enums import UserRole


async def _ingest(live: bool, force: bool) -> None:
    from app.legal.ingestion import ingest_all

    async with session_scope() as db:
        for r in await ingest_all(db, fetch_live=live, force=force):
            print(f"{r.document_key}: {r.status} ({r.chunks} chunks){' - ' + r.detail if r.detail else ''}")


async def _create_admin(email: str, name: str) -> None:
    password = sys.stdin.readline().strip() if not sys.stdin.isatty() else getpass.getpass("Password: ")
    if len(password) < 12:
        raise SystemExit("Admin password must be at least 12 characters.")
    async with session_scope() as db:
        if await db.scalar(select(User).where(User.email == email.lower())):
            raise SystemExit("A user with that email exists.")
        user = User(email=email.lower(), full_name=name, password_hash=hash_password(password), role=UserRole.ADMIN)
        user.preferences = UserPreferences(language="en")
        db.add(user)
    print(f"Admin {email} created.")


async def _reminders() -> None:
    from app.services.notifications import send_deadline_reminders

    async with session_scope() as db:
        print(await send_deadline_reminders(db))


async def _init_sqlite() -> None:
    if not get_settings().is_sqlite:
        raise SystemExit("init-sqlite is for local SQLite only. Use `alembic upgrade head` for PostgreSQL.")
    from app.db.base import Base

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("SQLite tables created.")


def main() -> None:
    configure_logging("WARNING")
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("--live", action="store_true", help="re-download from the official URLs")
    ingest.add_argument("--force", action="store_true", help="re-chunk even if unchanged")
    admin = sub.add_parser("create-admin")
    admin.add_argument("email")
    admin.add_argument("name")
    sub.add_parser("reminders")
    sub.add_parser("init-sqlite")
    args = parser.parse_args()
    if args.cmd == "ingest":
        asyncio.run(_ingest(args.live, args.force))
    elif args.cmd == "create-admin":
        asyncio.run(_create_admin(args.email, args.name))
    elif args.cmd == "reminders":
        asyncio.run(_reminders())
    elif args.cmd == "init-sqlite":
        asyncio.run(_init_sqlite())


if __name__ == "__main__":
    main()
