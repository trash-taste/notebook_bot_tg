from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.storage.models import Task


class TaskRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        capture_item_id: int | None,
        user_id: int | None,
        title: str,
        status: str = "active",
        due_at_utc: datetime | None = None,
        due_type: str | None = None,
        priority: str | None = None,
        created_at_utc: datetime | None = None,
    ) -> Task:
        now = _utc(created_at_utc)
        task = Task(
            capture_item_id=capture_item_id,
            user_id=user_id,
            title=title,
            status=status,
            due_at_utc=_utc(due_at_utc) if due_at_utc else None,
            due_type=due_type,
            priority=priority,
            created_at_utc=now,
            updated_at_utc=now,
            archived_at_utc=None,
        )
        self.session.add(task)
        self.session.flush()
        return task

    def get(self, task_id: int) -> Task | None:
        return self.session.get(Task, task_id)

    def active_for_user(self, user_id: int, *, limit: int = 50) -> list[Task]:
        return list(
            self.session.scalars(
                select(Task)
                .where(
                    Task.user_id == user_id,
                    Task.status == "active",
                    Task.archived_at_utc.is_(None),
                )
                .order_by(Task.created_at_utc.desc())
                .limit(limit)
            )
        )

    def mark_done(self, task_id: int) -> Task | None:
        task = self.get(task_id)
        if task is None:
            return None
        task.status = "done"
        task.updated_at_utc = _utc(None)
        self.session.flush()
        return task

    def archive(self, task_id: int) -> Task | None:
        task = self.get(task_id)
        if task is None:
            return None
        now = _utc(None)
        task.status = "archived"
        task.archived_at_utc = now
        task.updated_at_utc = now
        self.session.flush()
        return task


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)
