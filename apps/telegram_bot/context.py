from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apps.telegram_bot.db import Database


@dataclass(frozen=True)
class BotContext:
    user_id: int
    current_date: str
    timezone_name: str
    recent_items: list[dict[str, Any]]
    today_items: list[dict[str, Any]]
    active_tasks: list[dict[str, Any]]
    last_workout: dict[str, Any] | None
    last_food: dict[str, Any] | None
    last_general_note: dict[str, Any] | None
    last_note: dict[str, Any] | None
    last_changed_item: dict[str, Any] | None
    preferred_type: str | None
    daily_note_path: Path | None

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "current_date": self.current_date,
            "timezone": self.timezone_name,
            "preferred_type_from_keywords": self.preferred_type,
            "recent_items": [_item_summary(item) for item in self.recent_items],
            "today_items": [_item_summary(item) for item in self.today_items],
            "active_tasks": [_item_summary(item) for item in self.active_tasks],
            "last_workout": _item_summary(self.last_workout),
            "last_food": _item_summary(self.last_food),
            "last_general_note": _item_summary(self.last_general_note),
            "last_note": self.last_note,
            "last_changed_item": _item_summary(self.last_changed_item),
            "daily_note_path": str(self.daily_note_path) if self.daily_note_path else None,
        }


def collect_context(
    database: Database,
    *,
    user_id: int,
    timezone_name: str,
    user_text: str,
    obsidian_vault_path: Path | None,
) -> BotContext:
    local_date, start_utc, end_utc = local_day_bounds(timezone_name)
    recent_items = database.get_recent_items(user_id, limit=10)
    today_items = database.get_items_for_local_date(
        user_id,
        local_date,
        start_utc,
        end_utc,
    )
    daily_note_path = (
        obsidian_vault_path / "Daily" / f"{local_date}.md"
        if obsidian_vault_path is not None
        else None
    )
    return BotContext(
        user_id=user_id,
        current_date=local_date,
        timezone_name=timezone_name,
        recent_items=recent_items,
        today_items=today_items,
        active_tasks=database.get_active_tasks(user_id),
        last_workout=database.get_last_item_by_type(user_id, "workout_log"),
        last_food=database.get_last_item_by_type(user_id, "food_log"),
        last_general_note=database.get_last_item_by_type(user_id, "general_note"),
        last_note=database.get_last_note(user_id),
        last_changed_item=database.get_last_changed_item(user_id),
        preferred_type=detect_preferred_type(user_text),
        daily_note_path=daily_note_path,
    )


def local_day_bounds(timezone_name: str) -> tuple[str, str, str]:
    try:
        tzinfo = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"Unknown timezone: {timezone_name}") from exc

    now = datetime.now(tzinfo)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return (
        start.date().isoformat(),
        start.astimezone(timezone.utc).isoformat(timespec="seconds"),
        end.astimezone(timezone.utc).isoformat(timespec="seconds"),
    )


def day_bounds_for_date(local_date: str, timezone_name: str) -> tuple[str, str, str]:
    try:
        tzinfo = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"Unknown timezone: {timezone_name}") from exc
    day = datetime.fromisoformat(local_date).date()
    start = datetime(day.year, day.month, day.day, tzinfo=tzinfo)
    end = start + timedelta(days=1)
    return (
        local_date,
        start.astimezone(timezone.utc).isoformat(timespec="seconds"),
        end.astimezone(timezone.utc).isoformat(timespec="seconds"),
    )


def detect_preferred_type(text: str) -> str | None:
    lowered = text.lower()
    keyword_groups = [
        (
            "food_log",
            [
                "еда",
                "питание",
                "съел",
                "съела",
                "завтрак",
                "обед",
                "ужин",
                "яйц",
                "греч",
                "куриц",
                "кофе",
                "чай",
            ],
        ),
        (
            "workout_log",
            [
                "трен",
                "упраж",
                "жим",
                "тяга",
                "подход",
                "повтор",
                "гантел",
                "штанг",
                "блок",
            ],
        ),
        (
            "task",
            ["задач", "надо", "купить", "сделать", "напомни", "перенеси"],
        ),
        (
            "general_note",
            ["идея", "мысль", "заметка", "проект", "это к"],
        ),
    ]
    for item_type, keywords in keyword_groups:
        if any(keyword in lowered for keyword in keywords):
            return item_type
    return None


def context_to_text(context: BotContext) -> str:
    lines = ["Контекст сейчас:"]
    lines.extend(["", "Последняя тренировка:"])
    lines.append(_item_line(context.last_workout))
    lines.extend(["", "Последнее питание:"])
    lines.append(_item_line(context.last_food))
    lines.extend(["", "Активные задачи:"])
    if context.active_tasks:
        lines.extend(f"— {task['title']}, {_date_label(task)}" for task in context.active_tasks[:5])
    else:
        lines.append("— нет")
    lines.extend(["", "Последние записи:"])
    if context.recent_items:
        for index, item in enumerate(context.recent_items[:5], start=1):
            lines.append(f"{index}. {item['type']}: {item['title']}")
    else:
        lines.append("— нет")
    lines.extend(["", "Последняя запись:"])
    lines.append(
        f"— {context.last_note['raw_text']}"
        if context.last_note
        else "— нет"
    )
    lines.extend(["", "Obsidian Daily note:"])
    lines.append(f"— {context.daily_note_path}" if context.daily_note_path else "— не настроен")
    return "\n".join(lines)


def _item_summary(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "id": item.get("id"),
        "note_id": item.get("note_id"),
        "type": item.get("type"),
        "title": item.get("title"),
        "date": item.get("date"),
        "due_type": item.get("due_type"),
        "due_date": item.get("due_date"),
        "priority": item.get("priority"),
        "status": item.get("status"),
        "data": _json_object(item.get("data_json")),
        "raw_fragment": item.get("raw_fragment"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def _json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _item_line(item: dict[str, Any] | None) -> str:
    if item is None:
        return "— нет"
    return f"— {item['title']}, {_date_label(item)}"


def _date_label(item: dict[str, Any]) -> str:
    if item.get("due_date"):
        return str(item["due_date"])
    if item.get("date"):
        return str(item["date"])
    return "без даты"
