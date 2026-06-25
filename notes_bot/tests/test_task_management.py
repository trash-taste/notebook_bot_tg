from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


NOTES_BOT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(NOTES_BOT_ROOT))

from app.db import Database
from app.handlers import due_date_for_type
from app.keyboards import delete_confirmation_keyboard, reschedule_keyboard, tasks_keyboard
from app.models import ParsedNote


def parsed_note() -> ParsedNote:
    return ParsedNote.model_validate(
        {
            "raw_text": "доделать бота",
            "detected_language": "ru",
            "items": [
                {
                    "type": "task",
                    "category": "task",
                    "title": "Доделать бота",
                    "date": "2026-06-23",
                    "due_type": "no_deadline",
                    "due_date": None,
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


class TaskManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "notes.db")
        self.database.initialize()
        self.database.save_note(
            10,
            "доделать бота",
            parsed_note(),
            created_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
        )
        self.task_id = self.database.get_active_tasks(10)[0]["id"]

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_rename_reschedule_complete_and_delete_are_owner_scoped(self) -> None:
        self.assertFalse(self.database.rename_task(999, self.task_id, "Чужая задача"))
        self.assertTrue(self.database.rename_task(10, self.task_id, "Доделать Telegram-бота"))
        self.assertEqual(
            self.database.get_task(10, self.task_id)["title"],
            "Доделать Telegram-бота",
        )

        self.assertTrue(
            self.database.reschedule_task(10, self.task_id, "tomorrow", "2026-06-24")
        )
        task = self.database.get_task(10, self.task_id)
        self.assertEqual(task["due_type"], "tomorrow")
        self.assertEqual(task["due_date"], "2026-06-24")

        self.assertTrue(self.database.complete_task(10, self.task_id))
        self.assertEqual(self.database.get_active_tasks(10), [])
        self.assertFalse(self.database.delete_task(999, self.task_id))
        self.assertTrue(self.database.delete_task(10, self.task_id))
        self.assertIsNone(self.database.get_task(10, self.task_id))

        events = self.database.get_item_events(10, self.task_id)
        self.assertEqual(
            [event["event_type"] for event in events],
            ["created", "updated", "updated", "updated", "archived"],
        )

    def test_task_keyboards_contain_expected_actions(self) -> None:
        task = self.database.get_task(10, self.task_id)
        callbacks = [
            button.callback_data
            for row in tasks_keyboard([task]).inline_keyboard
            for button in row
        ]
        self.assertEqual(
            callbacks,
            [
                f"task:done:{self.task_id}",
                f"task:edit:{self.task_id}",
                f"task:move:{self.task_id}",
                f"task:delete:{self.task_id}",
            ],
        )
        self.assertEqual(
            reschedule_keyboard(self.task_id).inline_keyboard[0][0].callback_data,
            f"task:due:{self.task_id}:today",
        )
        self.assertEqual(
            delete_confirmation_keyboard(self.task_id)
            .inline_keyboard[0][0]
            .callback_data,
            f"task:delete_yes:{self.task_id}",
        )

    def test_due_date_helper(self) -> None:
        self.assertIsNotNone(due_date_for_type("today", "Asia/Almaty"))
        self.assertIsNotNone(due_date_for_type("tomorrow", "Asia/Almaty"))
        self.assertIsNone(due_date_for_type("this_week", "Asia/Almaty"))
        self.assertIsNone(due_date_for_type("no_deadline", "Asia/Almaty"))


if __name__ == "__main__":
    unittest.main()
