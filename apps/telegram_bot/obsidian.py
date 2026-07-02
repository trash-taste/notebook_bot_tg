from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BOT_BLOCK_START = "<!-- BOT-GENERATED:START -->"
BOT_BLOCK_END = "<!-- BOT-GENERATED:END -->"


class ObsidianExporter:
    def __init__(self, vault_path: Path | None, *, enabled: bool = True) -> None:
        self.vault_path = vault_path
        self.export_enabled = enabled

    @property
    def enabled(self) -> bool:
        return self.export_enabled and self.vault_path is not None

    def daily_note_path(self, date: str) -> Path | None:
        if self.vault_path is None:
            return None
        return self.vault_path / "Daily" / f"{date}.md"

    def rebuild_daily_note(
        self,
        *,
        user_id: int,
        date: str,
        items: list[dict[str, Any]],
    ) -> Path | None:
        if not self.enabled:
            return None

        path = self.daily_note_path(date)
        if path is None:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)

        existing = path.read_text(encoding="utf-8") if path.exists() else _daily_template(date)
        generated_block = _render_generated_block(user_id=user_id, items=items)
        updated = _replace_generated_block(existing, date, generated_block)
        path.write_text(updated, encoding="utf-8")
        return path


def _daily_template(date: str) -> str:
    return "\n".join(
        [
            f"# {date}",
            "",
            "## 📝 Ручные мысли",
            "",
            "",
            BOT_BLOCK_START,
            BOT_BLOCK_END,
            "",
        ]
    )


def _replace_generated_block(existing: str, date: str, generated_block: str) -> str:
    if BOT_BLOCK_START in existing and BOT_BLOCK_END in existing:
        before, rest = existing.split(BOT_BLOCK_START, 1)
        _, after = rest.split(BOT_BLOCK_END, 1)
        return f"{before}{generated_block}{after}"

    base = existing.rstrip()
    if not base:
        base = _daily_template(date).rstrip()
        before, rest = base.split(BOT_BLOCK_START, 1)
        _, after = rest.split(BOT_BLOCK_END, 1)
        return f"{before}{generated_block}{after}\n"
    return f"{base}\n\n{generated_block}\n"


def _render_generated_block(*, user_id: int, items: list[dict[str, Any]]) -> str:
    groups = [
        ("task", "✅ Задачи"),
        ("food_log", "🍽 Питание"),
        ("workout_log", "🏋️ Тренировка"),
        ("general_note", "🧠 Заметки"),
    ]
    lines = [BOT_BLOCK_START, f"<!-- user:{user_id} -->", ""]
    for item_type, heading in groups:
        lines.extend([heading, ""])
        typed_items = [item for item in items if item.get("type") == item_type]
        if typed_items:
            for item in typed_items:
                lines.extend(_render_item_block(item))
                lines.append("")
        else:
            lines.append("_Нет записей._")
            lines.append("")
    lines.append(BOT_BLOCK_END)
    return "\n".join(lines)


def _render_item_block(item: dict[str, Any]) -> list[str]:
    block_id = item.get("obsidian_block_id") or _block_id(item.get("type"), item.get("id"))
    return [
        f"<!-- item:{block_id} -->",
        *_item_lines(item),
        f"<!-- /item:{block_id} -->",
    ]


def _item_lines(item: dict[str, Any]) -> list[str]:
    item_type = item.get("type")
    data = _json_object(item.get("data_json"))
    if item_type == "task":
        checkbox = "- [x]" if item.get("status") == "done" else "- [ ]"
        due = f" 📅 {item['due_date']}" if item.get("due_date") else ""
        return [f"{checkbox} {item.get('title', 'Задача')}{due}"]
    if item_type == "workout_log":
        lines = _data_list(data, "exercises")
        return lines or [f"- {item.get('title', 'Тренировка')}"]
    if item_type == "food_log":
        lines = _data_list(data, "items")
        return lines or [f"- {item.get('title', 'Питание')}"]
    return [f"- {item.get('title', 'Заметка')}"]


def _data_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list):
        return []
    lines = []
    for entry in value:
        if isinstance(entry, str):
            lines.append(f"- {entry}")
        elif isinstance(entry, dict):
            lines.append(f"- {_format_data_entry(entry)}")
    return lines


def _format_data_entry(entry: dict[str, Any]) -> str:
    name = entry.get("name") or entry.get("exercise") or entry.get("title") or "Запись"
    details = []
    for key, label in [
        ("amount", ""),
        ("weight_kg", "кг"),
        ("reps", "повт."),
        ("sets_count", "подх."),
    ]:
        value = entry.get(key)
        if value is not None:
            details.append(f"{value} {label}".strip())
    if details:
        return f"{name}: {', '.join(details)}"
    compact = {
        key: value
        for key, value in entry.items()
        if key not in {"name", "exercise", "title"} and value is not None
    }
    if compact:
        return f"{name} — {json.dumps(compact, ensure_ascii=False)}"
    return str(name)


def _json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _block_id(item_type: str | None, item_id: object) -> str:
    short = {
        "task": "task",
        "workout_log": "workout",
        "food_log": "food",
        "general_note": "note",
    }.get(str(item_type), "item")
    return f"{short}-{item_id}"
