from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


TODAY_BUTTON = "📅 Сегодня"
TASKS_BUTTON = "✅ Задачи"
FOOD_BUTTON = "🍽 Питание"
WORKOUT_BUTTON = "🏋️ Тренировки"
LAST_BUTTON = "📝 Последняя"
UNDO_BUTTON = "↩️ Отменить последнюю"


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TODAY_BUTTON), KeyboardButton(text=TASKS_BUTTON)],
            [KeyboardButton(text=FOOD_BUTTON), KeyboardButton(text=WORKOUT_BUTTON)],
            [KeyboardButton(text=LAST_BUTTON), KeyboardButton(text=UNDO_BUTTON)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Напиши заметку обычным текстом",
    )

