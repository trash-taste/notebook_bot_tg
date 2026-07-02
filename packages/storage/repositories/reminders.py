from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.storage.models import Reminder


class ReminderRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        user_id: int | None,
        task_id: int | None,
        remind_at_utc: datetime,
        status: str = "active",
        created_at_utc: datetime | None = None,
    ) -> Reminder:
        reminder = Reminder(
            user_id=user_id,
            task_id=task_id,
            remind_at_utc=_utc(remind_at_utc),
            status=status,
            created_at_utc=_utc(created_at_utc),
        )
        self.session.add(reminder)
        self.session.flush()
        return reminder

    def due_before(self, moment_utc: datetime) -> list[Reminder]:
        return list(
            self.session.scalars(
                select(Reminder).where(
                    Reminder.status == "active",
                    Reminder.remind_at_utc <= _utc(moment_utc),
                )
            )
        )


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)
