from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packages.storage.db import create_schema, create_sqlite_engine, session_factory, session_scope
from packages.storage.repositories.capture_items import CaptureItemRepository
from packages.storage.repositories.notes import NoteRepository
from packages.storage.repositories.tasks import TaskRepository


@dataclass(frozen=True)
class ImportCounts:
    captures: int = 0
    notes: int = 0
    tasks: int = 0
    skipped_lines: int = 0


def import_jsonl_files(
    *,
    db_path: Path,
    notes_jsonl: Path,
    tasks_jsonl: Path,
) -> ImportCounts:
    engine = create_sqlite_engine(db_path)
    create_schema(engine)
    factory = session_factory(engine)

    captures = 0
    notes = 0
    tasks = 0
    skipped = 0

    with session_scope(factory) as session:
        capture_repo = CaptureItemRepository(session)
        note_repo = NoteRepository(session)
        task_repo = TaskRepository(session)

        if notes_jsonl.exists():
            for record in _read_jsonl(notes_jsonl):
                if record is None:
                    skipped += 1
                    continue
                capture = capture_repo.create(
                    raw_text=str(record.get("raw_text") or ""),
                    user_id=_int_or_none(record.get("user_id")),
                    chat_id=_int_or_none(record.get("chat_id")),
                    message_id=_int_or_none(record.get("message_id")),
                    source=str(record.get("source") or "text"),
                    status="imported",
                    created_at_utc=_parse_datetime(record.get("received_at")),
                )
                captures += 1
                parser_result = record.get("parser_result")
                if isinstance(parser_result, dict):
                    for item in parser_result.get("items", []):
                        if not isinstance(item, dict):
                            continue
                        note_repo.create(
                            capture_item_id=capture.id,
                            user_id=_int_or_none(record.get("user_id")),
                            type=str(item.get("type") or "general_note"),
                            category=str(item.get("category") or "general"),
                            title=str(item.get("title") or "Без названия"),
                            body=str(item.get("raw_fragment") or record.get("raw_text") or ""),
                            parsed_json=item,
                            created_at_utc=_parse_datetime(record.get("received_at")),
                        )
                        notes += 1

        if tasks_jsonl.exists():
            for record in _read_jsonl(tasks_jsonl):
                if record is None:
                    skipped += 1
                    continue
                task_repo.create(
                    capture_item_id=None,
                    user_id=_int_or_none(record.get("user_id")),
                    title=str(record.get("title") or "Без названия"),
                    status=str(record.get("status") or "active"),
                    due_at_utc=_parse_datetime(record.get("due_date")),
                    due_type=record.get("due_type"),
                    priority=record.get("priority"),
                    created_at_utc=_parse_datetime(record.get("created_at")),
                )
                tasks += 1

    return ImportCounts(
        captures=captures,
        notes=notes,
        tasks=tasks,
        skipped_lines=skipped,
    )


def _read_jsonl(path: Path) -> list[dict[str, Any] | None]:
    rows: list[dict[str, Any] | None] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            rows.append(None)
            continue
        rows.append(parsed if isinstance(parsed, dict) else None)
    return rows


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
