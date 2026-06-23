from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.telegram_bot.tasks import (
    active_tasks_for_chat,
    append_tasks_from_parser_result,
    format_due,
    mark_task_done,
    read_task_records,
    rename_task,
    reschedule_task,
)
from tests.test_validate import valid_payload


TASKS_TEST_PATH = Path("tests") / "_tasks_test.jsonl"


class TaskStorageTests(unittest.TestCase):
    def tearDown(self) -> None:
        TASKS_TEST_PATH.unlink(missing_ok=True)
        TASKS_TEST_PATH.with_name(TASKS_TEST_PATH.name + ".tmp").unlink(missing_ok=True)

    def test_append_tasks_from_parser_result_stores_only_task_items(self) -> None:
        payload = valid_payload()
        payload["items"].append(
            {
                "type": "food_log",
                "category": "food",
                "title": "Гречка",
                "date": "2026-01-15",
                "due_type": None,
                "due_date": None,
                "priority": None,
                "status": None,
                "data": {},
                "raw_fragment": "ел гречку",
                "missing_fields": [],
                "confidence": 0.7,
                "needs_clarification": False,
            }
        )

        records = append_tasks_from_parser_result(
            payload,
            chat_id=10,
            user_id=20,
            source_message_id=123,
            path=TASKS_TEST_PATH,
            now=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
        )
        stored = read_task_records(path=TASKS_TEST_PATH)

        self.assertEqual(len(records), 1)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["chat_id"], 10)
        self.assertEqual(stored[0]["user_id"], 20)
        self.assertEqual(stored[0]["source_message_id"], 123)
        self.assertEqual(stored[0]["title"], "Купить магний")
        self.assertEqual(stored[0]["status"], "active")

    def test_active_tasks_for_chat_filters_chat_and_status(self) -> None:
        payload = valid_payload()
        first = append_tasks_from_parser_result(
            payload,
            chat_id=10,
            user_id=20,
            source_message_id=1,
            path=TASKS_TEST_PATH,
        )[0]
        append_tasks_from_parser_result(
            payload,
            chat_id=999,
            user_id=20,
            source_message_id=2,
            path=TASKS_TEST_PATH,
        )
        mark_task_done(first["task_id"], path=TASKS_TEST_PATH)

        self.assertEqual(active_tasks_for_chat(10, path=TASKS_TEST_PATH), [])
        self.assertEqual(len(active_tasks_for_chat(999, path=TASKS_TEST_PATH)), 1)

    def test_mark_done_rename_and_reschedule_update_task(self) -> None:
        task = append_tasks_from_parser_result(
            valid_payload(),
            chat_id=10,
            user_id=20,
            source_message_id=1,
            path=TASKS_TEST_PATH,
            now=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
        )[0]

        renamed = rename_task(
            task["task_id"],
            "Купить магний и цинк",
            path=TASKS_TEST_PATH,
            now=datetime(2026, 1, 15, 11, 0, tzinfo=timezone.utc),
        )
        rescheduled = reschedule_task(
            task["task_id"],
            "tomorrow",
            user_timezone="Asia/Almaty",
            path=TASKS_TEST_PATH,
            now=datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc),
        )
        done = mark_task_done(
            task["task_id"],
            path=TASKS_TEST_PATH,
            now=datetime(2026, 1, 15, 13, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(renamed["title"], "Купить магний и цинк")
        self.assertEqual(rescheduled["due_type"], "tomorrow")
        self.assertEqual(rescheduled["due_date"], "2026-01-16")
        self.assertEqual(done["status"], "done")

    def test_format_due_labels(self) -> None:
        self.assertEqual(format_due({"due_type": "today"}), "сегодня")
        self.assertEqual(format_due({"due_type": "tomorrow"}), "завтра")
        self.assertEqual(format_due({"due_type": "this_week"}), "на этой неделе")
        self.assertEqual(
            format_due({"due_type": "specific_date", "due_date": "2026-07-05"}),
            "2026-07-05",
        )
        self.assertEqual(format_due({"due_type": "no_deadline"}), "без срока")


if __name__ == "__main__":
    unittest.main()
