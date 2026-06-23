from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models import ParsedNote


SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    raw_text TEXT NOT NULL,
    parsed_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_notes_user_created
ON raw_notes(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    date TEXT,
    due_type TEXT,
    due_date TEXT,
    priority TEXT,
    status TEXT,
    data_json TEXT NOT NULL,
    raw_fragment TEXT NOT NULL,
    confidence REAL NOT NULL,
    needs_clarification INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(note_id) REFERENCES raw_notes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_items_user_type_created
ON items(user_id, type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_items_tasks
ON items(user_id, type, status, due_date);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            with connection:
                connection.executescript(SCHEMA)

    def save_note(
        self,
        user_id: int,
        raw_text: str,
        parsed_note: ParsedNote,
        *,
        created_at: datetime | None = None,
    ) -> int:
        timestamp = _utc_iso(created_at)
        parsed_dict = parsed_note.model_dump(mode="json")
        parsed_json = json.dumps(parsed_dict, ensure_ascii=False, separators=(",", ":"))

        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO raw_notes(user_id, raw_text, parsed_json, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, raw_text, parsed_json, timestamp),
                )
                note_id = int(cursor.lastrowid)

                connection.executemany(
                    """
                    INSERT INTO items(
                        note_id, user_id, type, category, title, date, due_type,
                        due_date, priority, status, data_json, raw_fragment,
                        confidence, needs_clarification, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            note_id,
                            user_id,
                            item.type,
                            item.category,
                            item.title,
                            item.date.isoformat() if item.date else None,
                            item.due_type,
                            item.due_date.isoformat() if item.due_date else None,
                            item.priority,
                            item.status,
                            json.dumps(
                                item.data,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                            item.raw_fragment,
                            item.confidence,
                            int(item.needs_clarification),
                            timestamp,
                        )
                        for item in parsed_note.items
                    ],
                )
        return note_id

    def get_notes_between(
        self,
        user_id: int,
        start_utc: str,
        end_utc: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT id, user_id, raw_text, parsed_json, created_at
            FROM raw_notes
            WHERE user_id = ? AND created_at >= ? AND created_at < ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, start_utc, end_utc, limit),
        )

    def get_items_for_day(
        self,
        user_id: int,
        item_type: str,
        local_date: str,
        start_utc: str,
        end_utc: str,
        *,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT *
            FROM items
            WHERE user_id = ?
              AND type = ?
              AND (
                    date = ?
                    OR (date IS NULL AND created_at >= ? AND created_at < ?)
              )
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, item_type, local_date, start_utc, end_utc, limit),
        )

    def get_active_tasks(
        self,
        user_id: int,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT *
            FROM items
            WHERE user_id = ? AND type = 'task' AND status = 'active'
            ORDER BY
                CASE due_type
                    WHEN 'today' THEN 1
                    WHEN 'tomorrow' THEN 2
                    WHEN 'specific_date' THEN 3
                    WHEN 'this_week' THEN 4
                    ELSE 5
                END,
                due_date,
                created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )

    def get_task(self, user_id: int, task_id: int) -> dict[str, Any] | None:
        return self._fetch_one(
            """
            SELECT *
            FROM items
            WHERE id = ? AND user_id = ? AND type = 'task'
            """,
            (task_id, user_id),
        )

    def complete_task(self, user_id: int, task_id: int) -> bool:
        return self._update_task(
            user_id,
            task_id,
            "status = 'done'",
            (),
        )

    def rename_task(self, user_id: int, task_id: int, title: str) -> bool:
        normalized = " ".join(title.split())
        if not normalized:
            return False
        return self._update_task(
            user_id,
            task_id,
            "title = ?",
            (normalized,),
        )

    def reschedule_task(
        self,
        user_id: int,
        task_id: int,
        due_type: str,
        due_date: str | None,
    ) -> bool:
        if due_type not in {"today", "tomorrow", "this_week", "no_deadline"}:
            return False
        return self._update_task(
            user_id,
            task_id,
            "due_type = ?, due_date = ?",
            (due_type, due_date),
        )

    def delete_task(self, user_id: int, task_id: int) -> bool:
        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    DELETE FROM items
                    WHERE id = ? AND user_id = ? AND type = 'task'
                    """,
                    (task_id, user_id),
                )
                return cursor.rowcount == 1

    def get_last_note(self, user_id: int) -> dict[str, Any] | None:
        return self._fetch_one(
            """
            SELECT id, user_id, raw_text, parsed_json, created_at
            FROM raw_notes
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,),
        )

    def undo_last_note(self, user_id: int) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            with connection:
                row = connection.execute(
                    """
                    SELECT id, user_id, raw_text, parsed_json, created_at
                    FROM raw_notes
                    WHERE user_id = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (user_id,),
                ).fetchone()
                if row is None:
                    return None

                connection.execute("DELETE FROM raw_notes WHERE id = ?", (row["id"],))
                return dict(row)

    def health_check(self) -> bool:
        with closing(self._connect()) as connection:
            return connection.execute("SELECT 1").fetchone()[0] == 1

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _fetch_all(
        self,
        query: str,
        params: tuple[Any, ...],
    ) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            return [dict(row) for row in connection.execute(query, params).fetchall()]

    def _fetch_one(
        self,
        query: str,
        params: tuple[Any, ...],
    ) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(query, params).fetchone()
            return dict(row) if row else None

    def _update_task(
        self,
        user_id: int,
        task_id: int,
        assignments: str,
        values: tuple[Any, ...],
    ) -> bool:
        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    f"""
                    UPDATE items
                    SET {assignments}
                    WHERE id = ? AND user_id = ? AND type = 'task'
                    """,
                    (*values, task_id, user_id),
                )
                return cursor.rowcount == 1


def _utc_iso(value: datetime | None) -> str:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat(timespec="seconds")
