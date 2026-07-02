from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.storage.models import Note


class NoteRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        capture_item_id: int | None,
        user_id: int | None,
        type: str,
        category: str,
        title: str,
        body: str | None,
        parsed_json: dict[str, Any],
        created_at_utc: datetime | None = None,
    ) -> Note:
        now = _utc(created_at_utc)
        note = Note(
            capture_item_id=capture_item_id,
            user_id=user_id,
            type=type,
            category=category,
            title=title,
            body=body,
            parsed_json=json.dumps(parsed_json, ensure_ascii=False, separators=(",", ":")),
            created_at_utc=now,
            updated_at_utc=now,
            archived_at_utc=None,
        )
        self.session.add(note)
        self.session.flush()
        return note

    def get(self, note_id: int) -> Note | None:
        return self.session.get(Note, note_id)

    def recent_for_user(self, user_id: int, *, limit: int = 20) -> list[Note]:
        return list(
            self.session.scalars(
                select(Note)
                .where(Note.user_id == user_id, Note.archived_at_utc.is_(None))
                .order_by(Note.created_at_utc.desc())
                .limit(limit)
            )
        )

    def archive(self, note_id: int) -> Note | None:
        note = self.get(note_id)
        if note is None:
            return None
        now = _utc(None)
        note.archived_at_utc = now
        note.updated_at_utc = now
        self.session.flush()
        return note


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)
