from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps.telegram_bot.models import ParsedNote


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
    updated_at TEXT,
    deleted_at TEXT,
    obsidian_file_path TEXT,
    obsidian_block_id TEXT,
    FOREIGN KEY(note_id) REFERENCES raw_notes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_items_user_type_created
ON items(user_id, type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_items_tasks
ON items(user_id, type, status, due_date);

CREATE TABLE IF NOT EXISTS item_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    old_data_json TEXT,
    new_data_json TEXT,
    raw_text TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_item_events_item_created
ON item_events(item_id, created_at DESC);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            with connection:
                connection.executescript(SCHEMA)
                self._migrate(connection)

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
                        confidence, needs_clarification, created_at, updated_at,
                        obsidian_block_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                            timestamp,
                            _block_id(item.type, 0),
                        )
                        for item in parsed_note.items
                    ],
                )
                rows = connection.execute(
                    """
                    SELECT id, type, data_json
                    FROM items
                    WHERE note_id = ?
                    ORDER BY id
                    """,
                    (note_id,),
                ).fetchall()
                for row in rows:
                    block_id = _block_id(row["type"], row["id"])
                    connection.execute(
                        "UPDATE items SET obsidian_block_id = ? WHERE id = ?",
                        (block_id, row["id"]),
                    )
                    self._insert_event(
                        connection,
                        item_id=row["id"],
                        user_id=user_id,
                        event_type="created",
                        old_data_json=None,
                        new_data_json=row["data_json"],
                        raw_text=raw_text,
                        created_at=timestamp,
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
              AND EXISTS (
                    SELECT 1 FROM items
                    WHERE items.note_id = raw_notes.id
                      AND COALESCE(items.status, 'active') NOT IN ('archived', 'deleted')
                      AND items.deleted_at IS NULL
              )
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
              AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
              AND deleted_at IS NULL
              AND (
                    date = ?
                    OR (date IS NULL AND created_at >= ? AND created_at < ?)
                    OR (updated_at >= ? AND updated_at < ?)
              )
            ORDER BY COALESCE(updated_at, created_at) DESC
            LIMIT ?
            """,
            (user_id, item_type, local_date, start_utc, end_utc, start_utc, end_utc, limit),
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
              AND deleted_at IS NULL
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
              AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
              AND deleted_at IS NULL
            """,
            (task_id, user_id),
        )

    def complete_task(self, user_id: int, task_id: int) -> bool:
        return self.update_item(user_id, task_id, {"status": "done"}, raw_text=None)

    def rename_task(self, user_id: int, task_id: int, title: str) -> bool:
        normalized = " ".join(title.split())
        if not normalized:
            return False
        return self.update_item(user_id, task_id, {"title": normalized}, raw_text=None)

    def reschedule_task(
        self,
        user_id: int,
        task_id: int,
        due_type: str,
        due_date: str | None,
    ) -> bool:
        if due_type not in {"today", "tomorrow", "this_week", "no_deadline"}:
            return False
        return self.update_item(
            user_id,
            task_id,
            {"due_type": due_type, "due_date": due_date},
            raw_text=None,
        )

    def delete_task(self, user_id: int, task_id: int) -> bool:
        return self.archive_item(user_id, task_id, raw_text=None)

    def get_item(self, user_id: int, item_id: int) -> dict[str, Any] | None:
        return self._fetch_one(
            """
            SELECT *
            FROM items
            WHERE id = ? AND user_id = ?
              AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
              AND deleted_at IS NULL
            """,
            (item_id, user_id),
        )

    def get_items_by_ids(
        self,
        user_id: int,
        item_ids: list[int],
    ) -> list[dict[str, Any]]:
        if not item_ids:
            return []
        placeholders = ",".join("?" for _ in item_ids)
        return self._fetch_all(
            f"""
            SELECT *
            FROM items
            WHERE user_id = ?
              AND id IN ({placeholders})
              AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
              AND deleted_at IS NULL
            ORDER BY created_at DESC
            """,
            (user_id, *item_ids),
        )

    def get_items_for_note(self, user_id: int, note_id: int) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT *
            FROM items
            WHERE user_id = ? AND note_id = ?
              AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
              AND deleted_at IS NULL
            ORDER BY id
            """,
            (user_id, note_id),
        )

    def get_item_events(self, user_id: int, item_id: int) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT *
            FROM item_events
            WHERE user_id = ? AND item_id = ?
            ORDER BY id
            """,
            (user_id, item_id),
        )

    def get_recent_items(self, user_id: int, *, limit: int = 10) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT *
            FROM items
            WHERE user_id = ?
              AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
              AND deleted_at IS NULL
            ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
            LIMIT ?
            """,
            (user_id, limit),
        )

    def get_items_for_local_date(
        self,
        user_id: int,
        local_date: str,
        start_utc: str,
        end_utc: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT *
            FROM items
            WHERE user_id = ?
              AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
              AND deleted_at IS NULL
              AND (
                    date = ?
                    OR due_date = ?
                    OR (date IS NULL AND created_at >= ? AND created_at < ?)
                    OR (updated_at >= ? AND updated_at < ?)
              )
            ORDER BY type, COALESCE(updated_at, created_at) DESC
            LIMIT ?
            """,
            (user_id, local_date, local_date, start_utc, end_utc, start_utc, end_utc, limit),
        )

    def get_last_item_by_type(
        self,
        user_id: int,
        item_type: str,
    ) -> dict[str, Any] | None:
        return self._fetch_one(
            """
            SELECT *
            FROM items
            WHERE user_id = ? AND type = ?
              AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
              AND deleted_at IS NULL
            ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
            LIMIT 1
            """,
            (user_id, item_type),
        )

    def get_last_changed_item(self, user_id: int) -> dict[str, Any] | None:
        return self._fetch_one(
            """
            SELECT *
            FROM items
            WHERE user_id = ?
              AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
              AND deleted_at IS NULL
            ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
            LIMIT 1
            """,
            (user_id,),
        )

    def append_item_data(
        self,
        user_id: int,
        item_id: int,
        data: dict[str, Any],
        *,
        raw_text: str | None,
    ) -> bool:
        item = self.get_item(user_id, item_id)
        if item is None:
            return False

        old_data = _json_object(item["data_json"])
        merged_data = _merge_data(old_data, data)
        title = item["title"]
        if item["type"] in {"food_log", "workout_log"}:
            title = _append_title(title, _data_title(data, raw_text))
        return self.update_item(
            user_id,
            item_id,
            {"title": title, "data": merged_data},
            raw_text=raw_text,
            event_type="appended",
        )

    def update_item(
        self,
        user_id: int,
        item_id: int,
        fields: dict[str, Any],
        *,
        raw_text: str | None,
        event_type: str = "updated",
    ) -> bool:
        allowed = {
            "title",
            "date",
            "due_type",
            "due_date",
            "priority",
            "status",
            "data",
        }
        values = {key: value for key, value in fields.items() if key in allowed}
        if not values:
            return False

        item = self.get_item(user_id, item_id)
        if item is None:
            return False

        timestamp = _utc_iso(None)
        old_data_json = item["data_json"]
        assignments: list[str] = []
        params: list[Any] = []
        for key, value in values.items():
            column = "data_json" if key == "data" else key
            assignments.append(f"{column} = ?")
            if key == "data":
                params.append(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
            else:
                params.append(value)
        assignments.append("updated_at = ?")
        params.append(timestamp)

        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    f"""
                    UPDATE items
                    SET {", ".join(assignments)}
                    WHERE id = ? AND user_id = ?
                      AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
                      AND deleted_at IS NULL
                    """,
                    (*params, item_id, user_id),
                )
                if cursor.rowcount != 1:
                    return False
                new_data_json = connection.execute(
                    "SELECT data_json FROM items WHERE id = ?",
                    (item_id,),
                ).fetchone()["data_json"]
                self._insert_event(
                    connection,
                    item_id=item_id,
                    user_id=user_id,
                    event_type=event_type,
                    old_data_json=old_data_json,
                    new_data_json=new_data_json,
                    raw_text=raw_text,
                    created_at=timestamp,
                )
                return True

    def archive_item(
        self,
        user_id: int,
        item_id: int,
        *,
        raw_text: str | None,
    ) -> bool:
        item = self.get_item(user_id, item_id)
        if item is None:
            return False
        timestamp = _utc_iso(None)
        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE items
                    SET status = 'archived', deleted_at = ?, updated_at = ?
                    WHERE id = ? AND user_id = ?
                      AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
                      AND deleted_at IS NULL
                    """,
                    (timestamp, timestamp, item_id, user_id),
                )
                if cursor.rowcount != 1:
                    return False
                self._insert_event(
                    connection,
                    item_id=item_id,
                    user_id=user_id,
                    event_type="archived",
                    old_data_json=item["data_json"],
                    new_data_json=item["data_json"],
                    raw_text=raw_text,
                    created_at=timestamp,
                )
                return True

    def get_last_note(self, user_id: int) -> dict[str, Any] | None:
        return self._fetch_one(
            """
            SELECT id, user_id, raw_text, parsed_json, created_at
            FROM raw_notes
            WHERE user_id = ?
              AND EXISTS (
                    SELECT 1 FROM items
                    WHERE items.note_id = raw_notes.id
                      AND COALESCE(items.status, 'active') NOT IN ('archived', 'deleted')
                      AND items.deleted_at IS NULL
              )
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
                      AND EXISTS (
                            SELECT 1 FROM items
                            WHERE items.note_id = raw_notes.id
                              AND COALESCE(items.status, 'active') NOT IN ('archived', 'deleted')
                              AND items.deleted_at IS NULL
                      )
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (user_id,),
                ).fetchone()
                if row is None:
                    return None

                timestamp = _utc_iso(None)
                items = connection.execute(
                    """
                    SELECT id, data_json
                    FROM items
                    WHERE note_id = ?
                      AND user_id = ?
                      AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
                      AND deleted_at IS NULL
                    """,
                    (row["id"], user_id),
                ).fetchall()
                connection.execute(
                    """
                    UPDATE items
                    SET status = 'archived', deleted_at = ?, updated_at = ?
                    WHERE note_id = ?
                      AND user_id = ?
                      AND COALESCE(status, 'active') NOT IN ('archived', 'deleted')
                      AND deleted_at IS NULL
                    """,
                    (timestamp, timestamp, row["id"], user_id),
                )
                for item in items:
                    self._insert_event(
                        connection,
                        item_id=item["id"],
                        user_id=user_id,
                        event_type="archived",
                        old_data_json=item["data_json"],
                        new_data_json=item["data_json"],
                        raw_text="undo_last_note",
                        created_at=timestamp,
                    )
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

    def _migrate(self, connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(items)").fetchall()
        }
        migrations = {
            "updated_at": "ALTER TABLE items ADD COLUMN updated_at TEXT",
            "deleted_at": "ALTER TABLE items ADD COLUMN deleted_at TEXT",
            "obsidian_file_path": "ALTER TABLE items ADD COLUMN obsidian_file_path TEXT",
            "obsidian_block_id": "ALTER TABLE items ADD COLUMN obsidian_block_id TEXT",
        }
        for column, statement in migrations.items():
            if column not in columns:
                connection.execute(statement)
        connection.execute(
            """
            UPDATE items
            SET updated_at = created_at
            WHERE updated_at IS NULL
            """
        )
        rows = connection.execute(
            """
            SELECT id, type
            FROM items
            WHERE obsidian_block_id IS NULL OR obsidian_block_id = ''
            """
        ).fetchall()
        for row in rows:
            connection.execute(
                "UPDATE items SET obsidian_block_id = ? WHERE id = ?",
                (_block_id(row["type"], row["id"]), row["id"]),
            )

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

    def _insert_event(
        self,
        connection: sqlite3.Connection,
        *,
        item_id: int,
        user_id: int,
        event_type: str,
        old_data_json: str | None,
        new_data_json: str | None,
        raw_text: str | None,
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO item_events(
                item_id, user_id, event_type, old_data_json, new_data_json,
                raw_text, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                user_id,
                event_type,
                old_data_json,
                new_data_json,
                raw_text,
                created_at,
            ),
        )


def _utc_iso(value: datetime | None) -> str:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat(timespec="seconds")


def _block_id(item_type: str, item_id: int) -> str:
    short = {
        "task": "task",
        "workout_log": "workout",
        "food_log": "food",
        "general_note": "note",
    }.get(item_type, "item")
    return f"{short}-{item_id}"


def _json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _merge_data(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    merged = dict(old)
    for key, value in new.items():
        if key in merged and isinstance(merged[key], list) and isinstance(value, list):
            merged[key] = [*merged[key], *value]
        elif key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _merge_data(merged[key], value)
        elif key in merged and key in {"items", "exercises", "sets", "notes"}:
            existing = merged[key] if isinstance(merged[key], list) else [merged[key]]
            incoming = value if isinstance(value, list) else [value]
            merged[key] = [*existing, *incoming]
        else:
            merged[key] = value
    return merged


def _data_title(data: dict[str, Any], raw_text: str | None) -> str:
    for key in ("exercise", "name", "title"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("items", "exercises"):
        value = data.get(key)
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, dict):
                for nested_key in ("name", "exercise", "title"):
                    nested = first.get(nested_key)
                    if isinstance(nested, str) and nested.strip():
                        return nested.strip()
            if isinstance(first, str) and first.strip():
                return first.strip()
    return " ".join((raw_text or "").split())[:80]


def _append_title(title: str, addition: str) -> str:
    if not addition or addition.lower() in title.lower():
        return title
    return f"{title}; {addition}"[:300]
