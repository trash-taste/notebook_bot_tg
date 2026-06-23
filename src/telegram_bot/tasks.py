from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.voice_note_parser.config import DEFAULT_USER_TIMEZONE, PROJECT_ROOT


TASKS_PATH = PROJECT_ROOT / "data" / "tasks.jsonl"
TASK_STATUSES = {"active", "done"}
RESCHEDULE_OPTIONS = {"today", "tomorrow", "this_week", "no_deadline"}


def append_tasks_from_parser_result(
    parser_result: dict[str, Any],
    *,
    chat_id: int | None,
    user_id: int | None,
    source_message_id: int | None,
    path: Path = TASKS_PATH,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    task_records = build_task_records_from_parser_result(
        parser_result,
        chat_id=chat_id,
        user_id=user_id,
        source_message_id=source_message_id,
        now=now,
    )
    append_task_records(task_records, path=path)
    return task_records


def build_task_records_from_parser_result(
    parser_result: dict[str, Any],
    *,
    chat_id: int | None,
    user_id: int | None,
    source_message_id: int | None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    created_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(
        timespec="seconds"
    )
    records: list[dict[str, Any]] = []

    for item in parser_result.get("items", []):
        if item.get("type") != "task":
            continue

        status = item.get("status") if item.get("status") in TASK_STATUSES else "active"
        records.append(
            {
                "task_id": uuid.uuid4().hex,
                "chat_id": chat_id,
                "user_id": user_id,
                "title": item.get("title") or "Без названия",
                "due_type": item.get("due_type") or "no_deadline",
                "due_date": item.get("due_date"),
                "priority": item.get("priority") or "normal",
                "status": status,
                "created_at": created_at,
                "updated_at": created_at,
                "source_message_id": source_message_id,
            }
        )

    return records


def append_task_records(
    records: list[dict[str, Any]],
    *,
    path: Path = TASKS_PATH,
) -> None:
    if not records:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        for record in records:
            json.dump(record, file, ensure_ascii=False, separators=(",", ":"))
            file.write("\n")


def read_task_records(*, path: Path = TASKS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def write_task_records(
    records: list[dict[str, Any]],
    *,
    path: Path = TASKS_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        for record in records:
            json.dump(record, file, ensure_ascii=False, separators=(",", ":"))
            file.write("\n")
    temp_path.replace(path)


def active_tasks_for_chat(
    chat_id: int | None,
    *,
    path: Path = TASKS_PATH,
) -> list[dict[str, Any]]:
    return [
        task
        for task in read_task_records(path=path)
        if task.get("chat_id") == chat_id and task.get("status") == "active"
    ]


def get_task(
    task_id: str,
    *,
    path: Path = TASKS_PATH,
) -> dict[str, Any] | None:
    for task in read_task_records(path=path):
        if task.get("task_id") == task_id:
            return task
    return None


def mark_task_done(
    task_id: str,
    *,
    path: Path = TASKS_PATH,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    return update_task(
        task_id,
        {"status": "done"},
        path=path,
        now=now,
    )


def rename_task(
    task_id: str,
    title: str,
    *,
    path: Path = TASKS_PATH,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    return update_task(
        task_id,
        {"title": title.strip()},
        path=path,
        now=now,
    )


def reschedule_task(
    task_id: str,
    due_type: str,
    *,
    user_timezone: str = DEFAULT_USER_TIMEZONE,
    path: Path = TASKS_PATH,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    if due_type not in RESCHEDULE_OPTIONS:
        return None

    due_date = due_date_for_due_type(
        due_type,
        user_timezone=user_timezone,
        now=now,
    )
    return update_task(
        task_id,
        {"due_type": due_type, "due_date": due_date},
        path=path,
        now=now,
    )


def update_task(
    task_id: str,
    updates: dict[str, Any],
    *,
    path: Path = TASKS_PATH,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    records = read_task_records(path=path)
    updated_task: dict[str, Any] | None = None
    updated_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(
        timespec="seconds"
    )

    for task in records:
        if task.get("task_id") != task_id:
            continue

        task.update(updates)
        task["updated_at"] = updated_at
        updated_task = task
        break

    if updated_task is None:
        return None

    write_task_records(records, path=path)
    return updated_task


def due_date_for_due_type(
    due_type: str,
    *,
    user_timezone: str = DEFAULT_USER_TIMEZONE,
    now: datetime | None = None,
) -> str | None:
    local_now = local_datetime(user_timezone, now=now)
    today = local_now.date()

    if due_type == "today":
        return today.isoformat()
    if due_type == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    return None


def format_due(task: dict[str, Any]) -> str:
    due_type = task.get("due_type")
    due_date = task.get("due_date")

    if due_type == "today":
        return "сегодня"
    if due_type == "tomorrow":
        return "завтра"
    if due_type == "this_week":
        return "на этой неделе"
    if due_type == "specific_date" and due_date:
        return str(due_date)
    if due_type == "unknown":
        return "срок непонятен"
    return "без срока"


def local_datetime(
    user_timezone: str,
    *,
    now: datetime | None = None,
) -> datetime:
    tzinfo = timezone_for(user_timezone)
    value = now or datetime.now(tzinfo)
    if value.tzinfo is None:
        return value.replace(tzinfo=tzinfo)
    return value.astimezone(tzinfo)


def timezone_for(user_timezone: str):
    try:
        return ZoneInfo(user_timezone)
    except ZoneInfoNotFoundError:
        return timezone.utc
