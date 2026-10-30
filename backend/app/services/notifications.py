"""In-app notifications and deadline reminders."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models import Case, Deadline, Notification, User
from app.models.enums import DeadlineStatus
from app.services.email import send_email


async def notify(
    db: AsyncSession, user_id: uuid.UUID, kind: str, title: str, body: str | None = None,
    case_id: uuid.UUID | None = None, link: str | None = None, dedupe_key: str | None = None,
) -> Notification | None:
    if dedupe_key and await db.scalar(select(Notification.id).where(Notification.dedupe_key == dedupe_key)):
        return None
    note = Notification(user_id=user_id, case_id=case_id, kind=kind, title=title[:300], body=body, link=link,
                        dedupe_key=dedupe_key)
    db.add(note)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        return None
    return note


async def send_deadline_reminders(db: AsyncSession, today: date | None = None) -> dict[str, int]:
    """Create reminders for open deadlines entering their reminder window. Idempotent."""
    today = today or date.today()
    rows = (await db.execute(
        select(Deadline, Case).join(Case, Deadline.case_id == Case.id)
        .where(Deadline.status == DeadlineStatus.OPEN, Deadline.due_date >= today,
               Deadline.due_date <= today + timedelta(days=60), Case.archived_at.is_(None))
    )).all()
    created = emailed = 0
    for deadline, case in rows:
        days = (deadline.due_date - today).days
        if days > deadline.reminder_days_before and days not in (1, 7):
            continue
        estimate = " (estimate)" if deadline.is_estimate else ""
        title = f"{deadline.title}{estimate}: {deadline.due_date:%d %b %Y} — {days} day(s) left"
        note = await notify(db, case.user_id, "deadline", title, deadline.basis, case.id,
                            f"/cases/{case.id}", dedupe_key=f"deadline:{deadline.id}:{days}")
        if note is not None:
            created += 1
            deadline.reminder_sent_at = utcnow()
            user = await db.get(User, case.user_id)
            if user and await send_email(user.email, "NyayaSetu reminder", f"{title}\n\nCase: {case.title}") == "sent":
                emailed += 1
    for deadline in (await db.scalars(select(Deadline).where(
            Deadline.status == DeadlineStatus.OPEN, Deadline.due_date < today))).all():
        deadline.status = DeadlineStatus.MISSED
    return {"reminders": created, "emailed": emailed}
