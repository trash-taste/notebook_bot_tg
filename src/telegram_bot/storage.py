from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.voice_note_parser.config import PROJECT_ROOT


NOTES_PATH = PROJECT_ROOT / "data" / "notes.jsonl"


def append_note_record(
    record: dict[str, Any],
    *,
    path: Path = NOTES_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        json.dump(record, file, ensure_ascii=False, separators=(",", ":"))
        file.write("\n")


def read_note_records(*, path: Path = NOTES_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records
