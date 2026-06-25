from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app.models import ParsedItem, ParsedNote


class ObsidianExporter:
    def __init__(self, vault_path: Path | None) -> None:
        self.vault_path = vault_path

    @property
    def enabled(self) -> bool:
        return self.vault_path is not None

    def export_note(
        self,
        *,
        user_id: int,
        note_id: int,
        raw_text: str,
        parsed_note: ParsedNote,
        created_at: datetime | None = None,
    ) -> Path | None:
        if self.vault_path is None:
            return None

        timestamp = _aware_utc(created_at)
        day = timestamp.date().isoformat()
        target_dir = self.vault_path / "Telegram" / day
        target_dir.mkdir(parents=True, exist_ok=True)

        title = _note_title(parsed_note, raw_text)
        file_name = f"{timestamp.strftime('%H%M%S')}-{note_id}-{_slug(title)}.md"
        target_path = target_dir / file_name
        target_path.write_text(
            _render_markdown(
                user_id=user_id,
                note_id=note_id,
                raw_text=raw_text,
                parsed_note=parsed_note,
                created_at=timestamp,
                title=title,
            ),
            encoding="utf-8",
        )
        return target_path


def _render_markdown(
    *,
    user_id: int,
    note_id: int,
    raw_text: str,
    parsed_note: ParsedNote,
    created_at: datetime,
    title: str,
) -> str:
    lines = [
        "---",
        f'title: "{_yaml_escape(title)}"',
        "source: telegram",
        f"user_id: {user_id}",
        f"telegram_note_id: {note_id}",
        f'created_at: "{created_at.isoformat(timespec="seconds")}"',
        "tags:",
        "  - telegram",
        "  - notes-bot",
        "---",
        "",
        f"# {title}",
        "",
        "## Исходный текст",
        "",
        raw_text.strip(),
        "",
        "## Разбор",
        "",
        parsed_note.bot_reply.strip(),
        "",
    ]

    groups = [
        ("task", "Задачи"),
        ("general_note", "Заметки"),
        ("workout_log", "Тренировки"),
        ("food_log", "Питание"),
    ]
    for item_type, heading in groups:
        items = [item for item in parsed_note.items if item.type == item_type]
        if not items:
            continue
        lines.extend([f"## {heading}", ""])
        for item in items:
            lines.extend(_item_lines(item))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _item_lines(item: ParsedItem) -> list[str]:
    prefix = "- [ ]" if item.type == "task" and item.status != "done" else "-"
    if item.type == "task" and item.status == "done":
        prefix = "- [x]"

    lines = [f"{prefix} {item.title}"]
    details = []
    if item.due_type:
        details.append(f"срок: {item.due_type}")
    if item.due_date:
        details.append(f"дата: {item.due_date.isoformat()}")
    if item.priority:
        details.append(f"приоритет: {item.priority}")
    if details:
        lines.append(f"  - {'; '.join(details)}")
    if item.data:
        lines.append(f"  - данные: `{json.dumps(item.data, ensure_ascii=False)}`")
    return lines


def _note_title(parsed_note: ParsedNote, raw_text: str) -> str:
    if parsed_note.items:
        return parsed_note.items[0].title[:80]
    normalized = " ".join(raw_text.split())
    return (normalized or "Telegram заметка")[:80]


def _slug(value: str) -> str:
    normalized = re.sub(r"[^\wа-яА-ЯёЁ-]+", "-", value.lower(), flags=re.UNICODE)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized[:60] or "note"


def _yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _aware_utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)
