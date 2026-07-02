from __future__ import annotations

import shutil
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


from apps.telegram_bot.db import Database
from apps.telegram_bot.handlers import due_date_for_type
from apps.telegram_bot.keyboards import delete_confirmation_keyboard, reschedule_keyboard, tasks_keyboard
from apps.telegram_bot.models import ParsedNote


def temporary_directory() -> Path:
    root = Path(__file__).resolve().parents[2] / "data" / "_test_tmp"
    path = root / f"tasks-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


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


def food_note() -> ParsedNote:
    return ParsedNote.model_validate(
        {
            "raw_text": "яичница",
            "detected_language": "ru",
            "items": [
                {
                    "type": "food_log",
                    "category": "food",
                    "title": "яичница",
                    "date": "2026-06-20",
                    "due_type": None,
                    "due_date": None,
                    "priority": None,
                    "status": "active",
                    "data": {"items": [{"name": "яичница", "amount": None}]},
                    "raw_fragment": "яичница",
                    "missing_fields": [],
                    "confidence": 0.95,
                    "needs_clarification": False,
                }
            ],
            "summary": {
                "tasks_count": 0,
                "workout_count": 0,
                "food_count": 1,
                "general_notes_count": 0,
            },
            "bot_reply": "Записал питание.",
        }
    )


class TaskManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = temporary_directory()
        self.database = Database(self.temp_dir / "notes.db")
        self.database.initialize()
        self.database.save_note(
            10,
            "доделать бота",
            parsed_note(),
            created_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
        )
        self.task_id = self.database.get_active_tasks(10)[0]["id"]

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

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

    def test_food_updated_today_is_visible_in_today_food(self) -> None:
        self.database.save_note(
            10,
            "яичница",
            food_note(),
            created_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
        )
        food_id = self.database.get_last_item_by_type(10, "food_log")["id"]

        self.assertTrue(
            self.database.append_item_data(
                10,
                food_id,
                {"items": [{"name": "яйца", "amount": "2 шт"}]},
                raw_text="Ты забыл про яичницу утром",
            )
        )

        now = datetime.now(timezone.utc)
        rows = self.database.get_items_for_day(
            10,
            "food_log",
            "2099-01-01",
            (now - timedelta(minutes=5)).isoformat(timespec="seconds"),
            (now + timedelta(minutes=5)).isoformat(timespec="seconds"),
        )
        self.assertTrue(any(row["id"] == food_id for row in rows))


if __name__ == "__main__":
    unittest.main()
