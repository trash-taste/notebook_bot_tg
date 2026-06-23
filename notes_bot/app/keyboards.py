from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


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


def tasks_keyboard(tasks: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, task in enumerate(tasks, start=1):
        task_id = task["id"]
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        text=f"{index}. ✅ Выполнено",
                        callback_data=f"task:done:{task_id}",
                    ),
                    InlineKeyboardButton(
                        text="✏️ Изменить",
                        callback_data=f"task:edit:{task_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="📅 Перенести",
                        callback_data=f"task:move:{task_id}",
                    ),
                    InlineKeyboardButton(
                        text="🗑 Удалить",
                        callback_data=f"task:delete:{task_id}",
                    ),
                ],
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reschedule_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Сегодня",
                    callback_data=f"task:due:{task_id}:today",
                ),
                InlineKeyboardButton(
                    text="Завтра",
                    callback_data=f"task:due:{task_id}:tomorrow",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="На этой неделе",
                    callback_data=f"task:due:{task_id}:this_week",
                ),
                InlineKeyboardButton(
                    text="Без срока",
                    callback_data=f"task:due:{task_id}:no_deadline",
                ),
            ],
        ]
    )


def delete_confirmation_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, удалить",
                    callback_data=f"task:delete_yes:{task_id}",
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data="task:cancel:0",
                ),
            ]
        ]
    )
