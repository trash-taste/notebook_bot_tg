from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


NOTES_BOT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(NOTES_BOT_ROOT))

from app.models import ParsedNote
from app.obsidian import ObsidianExporter


def parsed_note() -> ParsedNote:
    return ParsedNote.model_validate(
        {
            "raw_text": "доделать бота",
            "detected_language": "ru",
            "items": [
                {
                    "type": "task",
                    "category": "task",
                    "title": "Доделать Obsidian экспорт",
                    "date": "2026-06-25",
                    "due_type": "today",
                    "due_date": "2026-06-25",
                    "priority": "normal",
                    "status": "active",
                    "data": {},
                    "raw_fragment": "доделать бота",
                    "missing_fields": [],
                    "confidence": 0.95,
                    "needs_clarification": False,
                }
            ],
            "summary": {
                "tasks_count": 1,
                "workout_count": 0,
                "food_count": 0,
                "general_notes_count": 0,
            },
            "bot_reply": "Записал задачу.",
        }
    )


class ObsidianExportTests(unittest.TestCase):
    def test_export_note_writes_markdown_into_daily_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            exporter = ObsidianExporter(Path(temp_dir))

            path = exporter.export_note(
                user_id=10,
                note_id=25,
                raw_text="доделать бота",
                parsed_note=parsed_note(),
                created_at=datetime(2026, 6, 25, 12, 30, tzinfo=timezone.utc),
            )

            self.assertIsNotNone(path)
            assert path is not None
            self.assertEqual(path.parent, Path(temp_dir) / "Telegram" / "2026-06-25")
            content = path.read_text(encoding="utf-8")
            self.assertIn("source: telegram", content)
            self.assertIn("telegram_note_id: 25", content)
            self.assertIn("## Исходный текст", content)
            self.assertIn("доделать бота", content)
            self.assertIn("- [ ] Доделать Obsidian экспорт", content)

    def test_disabled_exporter_does_nothing(self) -> None:
        exporter = ObsidianExporter(None)

        path = exporter.export_note(
            user_id=10,
            note_id=25,
            raw_text="доделать бота",
            parsed_note=parsed_note(),
        )

        self.assertIsNone(path)


if __name__ == "__main__":
    unittest.main()
