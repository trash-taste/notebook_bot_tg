from __future__ import annotations

import json
import unittest

from packages.llm.validate import (
    ValidationError,
    parse_model_json,
    validate_parser_response,
)


def valid_payload() -> dict:
    return {
        "raw_text": "завтра купить магний",
        "detected_language": "ru",
        "items": [
            {
                "type": "task",
                "category": "task",
                "title": "Купить магний",
                "date": "2026-01-15",
                "due_type": "tomorrow",
                "due_date": "2026-01-16",
                "priority": "normal",
                "status": "active",
                "data": {},
                "raw_fragment": "завтра купить магний",
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
        "bot_reply": "Записал 1 задачу на завтра.",
    }


class ValidateTests(unittest.TestCase):
    def test_parse_model_json_requires_valid_json_object(self) -> None:
        with self.assertRaises(ValidationError):
            parse_model_json("не json")

        with self.assertRaises(ValidationError):
            parse_model_json("[]")

    def test_validate_accepts_valid_payload(self) -> None:
        payload = valid_payload()
        self.assertEqual(validate_parser_response(payload), payload)

    def test_validate_rejects_invalid_item_type(self) -> None:
        payload = valid_payload()
        payload["items"][0]["type"] = "task_today"

        with self.assertRaises(ValidationError):
            validate_parser_response(payload)

    def test_validate_rejects_summary_mismatch(self) -> None:
        payload = valid_payload()
        payload["summary"]["tasks_count"] = 0

        with self.assertRaises(ValidationError):
            validate_parser_response(payload)

    def test_json_round_trip_shape(self) -> None:
        payload = parse_model_json(json.dumps(valid_payload(), ensure_ascii=False))
        validate_parser_response(payload)


if __name__ == "__main__":
    unittest.main()

