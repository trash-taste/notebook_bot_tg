from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.storage.models import CaptureItem


class CaptureItemRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        raw_text: str,
        user_id: int | None,
        chat_id: int | None = None,
        message_id: int | None = None,
        source: str = "text",
        status: str = "received",
        created_at_utc: datetime | None = None,
    ) -> CaptureItem:
        now = _utc(created_at_utc)
        capture = CaptureItem(
            raw_text=raw_text,
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            source=source,
            status=status,
            parser_error=None,
            created_at_utc=now,
            updated_at_utc=now,
        )
        self.session.add(capture)
        self.session.flush()
        return capture

    def get(self, capture_id: int) -> CaptureItem | None:
        return self.session.get(CaptureItem, capture_id)

    def update_status(
        self,
        capture_id: int,
        *,
        status: str,
        parser_error: str | None = None,
    ) -> CaptureItem | None:
        capture = self.get(capture_id)
        if capture is None:
            return None
        capture.status = status
        capture.parser_error = parser_error
        capture.updated_at_utc = _utc(None)
        self.session.flush()
        return capture

    def recent_for_user(self, user_id: int, *, limit: int = 20) -> list[CaptureItem]:
        return list(
            self.session.scalars(
                select(CaptureItem)
                .where(CaptureItem.user_id == user_id)
                .order_by(CaptureItem.created_at_utc.desc())
                .limit(limit)
            )
        )


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)
