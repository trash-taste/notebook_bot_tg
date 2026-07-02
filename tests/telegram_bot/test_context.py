from __future__ import annotations

import unittest

from apps.telegram_bot.context import detect_preferred_type
from apps.telegram_bot.handlers import _prevent_accidental_append
from apps.telegram_bot.models import IntentResult


class ContextTests(unittest.TestCase):
    def test_detect_preferred_type_from_keywords(self) -> None:
        self.assertEqual(detect_preferred_type("Добавь туда 2 яйца"), "food_log")
        self.assertEqual(detect_preferred_type("Сегодня жим 70 на 8"), "workout_log")
        self.assertEqual(detect_preferred_type("Завтра купить магний"), "task")
        self.assertEqual(detect_preferred_type("Это к проекту бота"), "general_note")

    def test_plain_food_sentence_is_not_forced_into_append(self) -> None:
        intent = IntentResult(
            intent="append_to_existing_item",
            target_type="food_log",
            target_item_id=10,
            target_date="2026-06-25",
            action="append_food",
            data={"items": [{"name": "яйца", "amount": "2 шт"}]},
            confidence=0.9,
            needs_clarification=False,
        )

        result = _prevent_accidental_append(
            intent,
            "Сегодня я съел два яйца на завтрак",
        )

        self.assertEqual(result.intent, "create_new_item")
        self.assertIsNone(result.target_item_id)
        self.assertEqual(
            _prevent_accidental_append(intent, "Добавь туда 2 яйца").intent,
            "append_to_existing_item",
        )


if __name__ == "__main__":
    unittest.main()
