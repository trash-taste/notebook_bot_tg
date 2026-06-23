from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from src.telegram_bot.storage import append_note_record, read_note_records
from src.telegram_bot.tasks import (
    active_tasks_for_chat,
    append_tasks_from_parser_result,
    format_due,
    read_task_records,
    get_task,
    mark_task_done,
    rename_task,
    reschedule_task,
)
from src.voice_note_parser.config import ConfigError, Settings, load_settings
from src.voice_note_parser.openrouter import OpenRouterError
from src.voice_note_parser.prompt import PromptError
from src.voice_note_parser.service import ParserInputError, parse_transcript
from src.voice_note_parser.validate import ValidationError


LOGGER = logging.getLogger(__name__)
USER_ERROR_REPLY = (
    "Не получилось разобрать заметку. Проверь настройки API и попробуй еще раз."
)
VOICE_ERROR_REPLY = (
    "Голосовые отключены, чтобы не тратить деньги на распознавание. "
    "Надиктуй через клавиатуру телефона в текстовое поле и отправь текстом."
)
EDITING_TASK_ID_KEY = "editing_task_id"
MENU_TODAY = "📅 Сегодня"
MENU_TASKS = "✅ Задачи"
MENU_WORKOUTS = "🏋️ Тренировки"
MENU_FOOD = "🍽 Питание"
MENU_PROGRESS = "📈 Прогресс"
MENU_NOTES = "📝 Все заметки"
MENU_BUTTONS = {
    MENU_TODAY,
    MENU_TASKS,
    MENU_WORKOUTS,
    MENU_FOOD,
    MENU_PROGRESS,
    MENU_NOTES,
}


async def start(update: Any, context: Any) -> None:
    message = getattr(update, "message", None) or getattr(update, "effective_message", None)
    if message is None:
        return

    await message.reply_text(
        "Главное меню\nЧто показать?",
        reply_markup=build_main_menu_keyboard(),
    )


async def handle_text_message(update: Any, context: Any) -> None:
    message = getattr(update, "message", None) or getattr(update, "effective_message", None)
    if message is None:
        return

    raw_text = (getattr(message, "text", None) or "").strip()
    if not raw_text:
        await message.reply_text("Пришли текст заметки одним сообщением.")
        return

    if raw_text in MENU_BUTTONS:
        await handle_menu_button(update, context, raw_text)
        return

    user_data = getattr(context, "user_data", {})
    if user_data.get(EDITING_TASK_ID_KEY):
        await handle_task_title_edit(update, context, raw_text)
        return

    settings = context.bot_data["settings"]

    try:
        parser_result = await asyncio.to_thread(
            parse_transcript,
            raw_text,
            settings=settings,
        )
        record = build_note_record(update, raw_text, parser_result)
        await asyncio.to_thread(append_note_record, record)
        await asyncio.to_thread(
            save_tasks_from_parser_result,
            update,
            parser_result,
        )
    except (
        ConfigError,
        ParserInputError,
        PromptError,
        OpenRouterError,
        ValidationError,
        OSError,
    ):
        LOGGER.exception("Failed to parse Telegram message")
        await message.reply_text(USER_ERROR_REPLY)
        return

    await message.reply_text(parser_result.get("bot_reply") or "Записал заметку.")


async def menu_command(update: Any, context: Any) -> None:
    message = getattr(update, "message", None) or getattr(update, "effective_message", None)
    if message is None:
        return

    await message.reply_text(
        "Главное меню\nЧто показать?",
        reply_markup=build_main_menu_keyboard(),
    )


async def handle_menu_button(update: Any, context: Any, button_text: str) -> None:
    if button_text == MENU_TODAY:
        await today_command(update, context)
        return
    if button_text == MENU_TASKS:
        await tasks_command(update, context)
        return
    if button_text == MENU_WORKOUTS:
        await recent_items_command(update, "workout_log", "Последние тренировки")
        return
    if button_text == MENU_FOOD:
        await recent_items_command(update, "food_log", "Последнее питание")
        return
    if button_text == MENU_PROGRESS:
        await progress_command(update, context)
        return
    if button_text == MENU_NOTES:
        await notes_command(update)
        return


async def today_command(update: Any, context: Any) -> None:
    message = getattr(update, "message", None) or getattr(update, "effective_message", None)
    if message is None:
        return

    chat_id = getattr(getattr(update, "effective_chat", None), "id", None)
    tasks = await asyncio.to_thread(active_tasks_for_chat, chat_id)
    today_tasks = [task for task in tasks if task.get("due_type") == "today"]
    if not today_tasks:
        await message.reply_text("На сегодня активных задач нет.")
        return

    lines = ["Сегодня:"]
    for index, task in enumerate(today_tasks, start=1):
        lines.append(f"{index}. {task.get('title') or 'Без названия'}")
    await message.reply_text("\n".join(lines))


async def tasks_command(update: Any, context: Any) -> None:
    message = getattr(update, "message", None) or getattr(update, "effective_message", None)
    if message is None:
        return

    chat_id = getattr(getattr(update, "effective_chat", None), "id", None)
    tasks = await asyncio.to_thread(active_tasks_for_chat, chat_id)
    text, reply_markup = build_tasks_message(tasks)
    await reply_with_optional_markup(message, text, reply_markup)


async def handle_voice_message(update: Any, context: Any) -> None:
    message = getattr(update, "message", None) or getattr(update, "effective_message", None)
    if message is None:
        return

    await message.reply_text(VOICE_ERROR_REPLY, reply_markup=build_main_menu_keyboard())


async def handle_task_callback(update: Any, context: Any) -> None:
    query = getattr(update, "callback_query", None)
    if query is None:
        return

    await query.answer()
    data = getattr(query, "data", "") or ""
    parts = data.split(":")
    if len(parts) < 3 or parts[0] != "task":
        return

    action = parts[1]
    task_id = parts[2]
    settings = context.bot_data["settings"]

    if action == "done":
        updated = await asyncio.to_thread(mark_task_done, task_id)
        if updated is None:
            await edit_callback_message(query, "Задача не найдена.")
            return
        await refresh_tasks_callback_message(update, query)
        return

    if action == "reschedule":
        await edit_callback_message(
            query,
            "Куда перенести задачу?",
            build_reschedule_keyboard(task_id),
        )
        return

    if action == "due" and len(parts) == 4:
        due_type = parts[3]
        updated = await asyncio.to_thread(
            reschedule_task,
            task_id,
            due_type,
            user_timezone=settings.user_timezone,
        )
        if updated is None:
            await edit_callback_message(query, "Задача не найдена.")
            return
        await refresh_tasks_callback_message(update, query)
        return

    if action == "edit":
        task = await asyncio.to_thread(get_task, task_id)
        if task is None:
            await edit_callback_message(query, "Задача не найдена.")
            return
        user_data = getattr(context, "user_data", None)
        if user_data is None:
            user_data = {}
            context.user_data = user_data
        user_data[EDITING_TASK_ID_KEY] = task_id
        await edit_callback_message(query, "Отправь новое название задачи одним сообщением.")
        return

    await edit_callback_message(query, "Неизвестное действие.")


async def handle_task_title_edit(update: Any, context: Any, new_title: str) -> None:
    message = getattr(update, "message", None) or getattr(update, "effective_message", None)
    if message is None:
        return

    user_data = getattr(context, "user_data", {})
    task_id = user_data.pop(EDITING_TASK_ID_KEY, None)
    if not task_id:
        return

    updated = await asyncio.to_thread(rename_task, task_id, new_title)
    if updated is None:
        await message.reply_text("Задача не найдена.")
        return

    await message.reply_text(f"Изменил задачу: {updated['title']}")
    chat_id = getattr(getattr(update, "effective_chat", None), "id", None)
    tasks = await asyncio.to_thread(active_tasks_for_chat, chat_id)
    text, reply_markup = build_tasks_message(tasks)
    await reply_with_optional_markup(message, text, reply_markup)


async def refresh_tasks_callback_message(update: Any, query: Any) -> None:
    chat_id = getattr(getattr(update, "effective_chat", None), "id", None)
    tasks = await asyncio.to_thread(active_tasks_for_chat, chat_id)
    text, reply_markup = build_tasks_message(tasks)
    await edit_callback_message(query, text, reply_markup)


def save_tasks_from_parser_result(
    update: Any,
    parser_result: dict[str, Any],
) -> list[dict[str, Any]]:
    chat = getattr(update, "effective_chat", None)
    user = getattr(update, "effective_user", None)
    message = getattr(update, "message", None) or getattr(update, "effective_message", None)

    return append_tasks_from_parser_result(
        parser_result,
        chat_id=getattr(chat, "id", None),
        user_id=getattr(user, "id", None),
        source_message_id=getattr(message, "message_id", None),
    )


def build_tasks_message(tasks: list[dict[str, Any]]) -> tuple[str, Any | None]:
    if not tasks:
        return "Активных задач нет.", None

    lines = ["Активные задачи:", ""]
    for index, task in enumerate(tasks, start=1):
        lines.append(f"{index}. {task.get('title') or 'Без названия'} — {format_due(task)}")

    return "\n".join(lines), build_tasks_keyboard(tasks)


async def recent_items_command(update: Any, item_type: str, title: str) -> None:
    message = getattr(update, "message", None) or getattr(update, "effective_message", None)
    if message is None:
        return

    chat_id = getattr(getattr(update, "effective_chat", None), "id", None)
    records = await asyncio.to_thread(read_note_records)
    items = recent_items(records, chat_id=chat_id, item_type=item_type, limit=5)
    if not items:
        await message.reply_text(f"{title}: пока пусто.")
        return

    lines = [f"{title}:"]
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item.get('title') or 'Без названия'}")
    await message.reply_text("\n".join(lines))


async def notes_command(update: Any) -> None:
    message = getattr(update, "message", None) or getattr(update, "effective_message", None)
    if message is None:
        return

    chat_id = getattr(getattr(update, "effective_chat", None), "id", None)
    records = await asyncio.to_thread(read_note_records)
    notes = [record for record in records if record.get("chat_id") == chat_id][-5:]
    if not notes:
        await message.reply_text("Заметок пока нет.")
        return

    lines = ["Последние заметки:"]
    for index, record in enumerate(reversed(notes), start=1):
        raw_text = shorten(record.get("raw_text") or "", limit=70)
        lines.append(f"{index}. {raw_text}")
    await message.reply_text("\n".join(lines))


async def progress_command(update: Any, context: Any) -> None:
    message = getattr(update, "message", None) or getattr(update, "effective_message", None)
    if message is None:
        return

    chat_id = getattr(getattr(update, "effective_chat", None), "id", None)
    records = await asyncio.to_thread(read_note_records)
    tasks = await asyncio.to_thread(read_task_records)
    user_records = [record for record in records if record.get("chat_id") == chat_id]
    user_tasks = [task for task in tasks if task.get("chat_id") == chat_id]
    active_count = sum(1 for task in user_tasks if task.get("status") == "active")
    done_count = sum(1 for task in user_tasks if task.get("status") == "done")
    item_counts = count_items(user_records)

    await message.reply_text(
        "\n".join(
            [
                "Прогресс:",
                f"Активные задачи: {active_count}",
                f"Выполнено задач: {done_count}",
                f"Тренировки: {item_counts.get('workout_log', 0)}",
                f"Питание: {item_counts.get('food_log', 0)}",
                f"Заметки: {item_counts.get('general_note', 0)}",
            ]
        )
    )


def recent_items(
    records: list[dict[str, Any]],
    *,
    chat_id: int | None,
    item_type: str,
    limit: int,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in reversed(records):
        if record.get("chat_id") != chat_id:
            continue
        parser_result = record.get("parser_result") or {}
        for item in reversed(parser_result.get("items", [])):
            if item.get("type") == item_type:
                items.append(item)
                if len(items) >= limit:
                    return items
    return items


def count_items(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        parser_result = record.get("parser_result") or {}
        for item in parser_result.get("items", []):
            item_type = item.get("type")
            counts[item_type] = counts.get(item_type, 0) + 1
    return counts


def shorten(text: str, *, limit: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    shortened = normalized[: limit - 1].rstrip()
    if " " in shortened:
        shortened = shortened.rsplit(" ", 1)[0]
    return shortened + "…"


def build_main_menu_keyboard() -> Any:
    from telegram import KeyboardButton, ReplyKeyboardMarkup

    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(MENU_TODAY), KeyboardButton(MENU_TASKS)],
            [KeyboardButton(MENU_WORKOUTS), KeyboardButton(MENU_FOOD)],
            [KeyboardButton(MENU_PROGRESS), KeyboardButton(MENU_NOTES)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def build_tasks_keyboard(tasks: list[dict[str, Any]]) -> Any:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = []
    for index, task in enumerate(tasks, start=1):
        task_id = task["task_id"]
        rows.append(
            [
                InlineKeyboardButton(
                    f"{index}. ✅ Выполнено",
                    callback_data=f"task:done:{task_id}",
                ),
                InlineKeyboardButton(
                    "📆 Перенести",
                    callback_data=f"task:reschedule:{task_id}",
                ),
                InlineKeyboardButton(
                    "✏️ Изменить",
                    callback_data=f"task:edit:{task_id}",
                ),
            ]
        )
    return InlineKeyboardMarkup(rows)


def build_reschedule_keyboard(task_id: str) -> Any:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("сегодня", callback_data=f"task:due:{task_id}:today"),
                InlineKeyboardButton("завтра", callback_data=f"task:due:{task_id}:tomorrow"),
            ],
            [
                InlineKeyboardButton(
                    "эта неделя",
                    callback_data=f"task:due:{task_id}:this_week",
                ),
                InlineKeyboardButton(
                    "без срока",
                    callback_data=f"task:due:{task_id}:no_deadline",
                ),
            ],
        ]
    )


async def reply_with_optional_markup(message: Any, text: str, reply_markup: Any | None) -> None:
    if reply_markup is None:
        await message.reply_text(text)
    else:
        await message.reply_text(text, reply_markup=reply_markup)


async def edit_callback_message(
    query: Any,
    text: str,
    reply_markup: Any | None = None,
) -> None:
    message = getattr(query, "message", None)
    if message is None:
        return

    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except AttributeError:
        await message.reply_text(text)


def build_note_record(
    update: Any,
    raw_text: str,
    parser_result: dict[str, Any],
    *,
    source: str = "text",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    chat = getattr(update, "effective_chat", None)
    user = getattr(update, "effective_user", None)
    message = getattr(update, "message", None) or getattr(update, "effective_message", None)

    record = {
        "chat_id": getattr(chat, "id", None),
        "user_id": getattr(user, "id", None),
        "message_id": getattr(message, "message_id", None),
        "received_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "raw_text": raw_text,
        "parser_result": parser_result,
    }
    if extra:
        record.update(extra)

    return record


def build_application(settings: Settings):
    try:
        from telegram.ext import (
            Application,
            CallbackQueryHandler,
            CommandHandler,
            MessageHandler,
            filters,
        )
    except ImportError as exc:
        raise ConfigError(
            "Пакет python-telegram-bot не установлен. Выполни: "
            "python -m pip install -r requirements.txt"
        ) from exc

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data["settings"] = settings
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("tasks", tasks_command))
    application.add_handler(CallbackQueryHandler(handle_task_callback, pattern=r"^task:"))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )
    return application


def main() -> int:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )

    try:
        settings = load_settings(
            require_api_key=True,
            require_telegram_token=True,
        )
        application = build_application(settings)
    except ConfigError as exc:
        print(f"Ошибка: {exc}")
        return 1

    application.run_polling()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
