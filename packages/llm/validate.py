from __future__ import annotations

import json
from collections import Counter
from typing import Any


TOP_LEVEL_KEYS = {
    "raw_text",
    "detected_language",
    "items",
    "summary",
    "bot_reply",
}

ITEM_KEYS = {
    "type",
    "category",
    "title",
    "date",
    "due_type",
    "due_date",
    "priority",
    "status",
    "data",
    "raw_fragment",
    "missing_fields",
    "confidence",
    "needs_clarification",
}

ALLOWED_TYPES = {"task", "workout_log", "food_log", "general_note"}
CATEGORY_BY_TYPE = {
    "task": "task",
    "workout_log": "workout",
    "food_log": "food",
    "general_note": "general",
}
SUMMARY_KEYS = {
    "tasks_count",
    "workout_count",
    "food_count",
    "general_notes_count",
}


class ValidationError(ValueError):
    """Raised when model output is not valid parser JSON."""


def parse_model_json(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Ответ модели не является валидным JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValidationError("Ответ модели должен быть JSON-объектом.")

    return parsed


def validate_parser_response(data: dict[str, Any]) -> dict[str, Any]:
    keys = set(data)
    if keys != TOP_LEVEL_KEYS:
        missing = sorted(TOP_LEVEL_KEYS - keys)
        extra = sorted(keys - TOP_LEVEL_KEYS)
        details = []
        if missing:
            details.append("нет полей: " + ", ".join(missing))
        if extra:
            details.append("лишние поля: " + ", ".join(extra))
        raise ValidationError("Неверная top-level структура JSON: " + "; ".join(details))

    if not isinstance(data["items"], list):
        raise ValidationError("Поле items должно быть массивом.")
    if not isinstance(data["summary"], dict):
        raise ValidationError("Поле summary должно быть объектом.")
    if set(data["summary"]) != SUMMARY_KEYS:
        raise ValidationError("Поле summary содержит неверный набор счетчиков.")

    for index, item in enumerate(data["items"]):
        _validate_item(item, index)

    _validate_summary_counts(data["items"], data["summary"])
    return data


def _validate_item(item: Any, index: int) -> None:
    if not isinstance(item, dict):
        raise ValidationError(f"Item #{index + 1} должен быть объектом.")

    keys = set(item)
    if keys != ITEM_KEYS:
        missing = sorted(ITEM_KEYS - keys)
        extra = sorted(keys - ITEM_KEYS)
        details = []
        if missing:
            details.append("нет полей: " + ", ".join(missing))
        if extra:
            details.append("лишние поля: " + ", ".join(extra))
        raise ValidationError(
            f"Item #{index + 1} содержит неверную структуру: " + "; ".join(details)
        )

    item_type = item["type"]
    if item_type not in ALLOWED_TYPES:
        raise ValidationError(
            f"Item #{index + 1}: недопустимый type {item_type!r}."
        )

    expected_category = CATEGORY_BY_TYPE[item_type]
    if item["category"] != expected_category:
        raise ValidationError(
            f"Item #{index + 1}: category должен быть {expected_category!r}."
        )

    if not isinstance(item["missing_fields"], list):
        raise ValidationError(f"Item #{index + 1}: missing_fields должен быть массивом.")
    if not isinstance(item["data"], dict):
        raise ValidationError(f"Item #{index + 1}: data должен быть объектом.")
    if not isinstance(item["needs_clarification"], bool):
        raise ValidationError(
            f"Item #{index + 1}: needs_clarification должен быть boolean."
        )
    if not isinstance(item["confidence"], (int, float)):
        raise ValidationError(f"Item #{index + 1}: confidence должен быть числом.")


def _validate_summary_counts(items: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    counts = Counter(item["type"] for item in items)
    expected = {
        "tasks_count": counts["task"],
        "workout_count": counts["workout_log"],
        "food_count": counts["food_log"],
        "general_notes_count": counts["general_note"],
    }

    for key, expected_value in expected.items():
        actual_value = summary[key]
        if actual_value != expected_value:
            raise ValidationError(
                f"summary.{key} должен быть {expected_value}, получено {actual_value}."
            )

