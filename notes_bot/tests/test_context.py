from __future__ import annotations

import unittest

from app.context import detect_preferred_type


class ContextTests(unittest.TestCase):
    def test_detect_preferred_type_from_keywords(self) -> None:
        self.assertEqual(detect_preferred_type("Добавь туда 2 яйца"), "food_log")
        self.assertEqual(detect_preferred_type("Сегодня жим 70 на 8"), "workout_log")
        self.assertEqual(detect_preferred_type("Завтра купить магний"), "task")
        self.assertEqual(detect_preferred_type("Это к проекту бота"), "general_note")


if __name__ == "__main__":
    unittest.main()
