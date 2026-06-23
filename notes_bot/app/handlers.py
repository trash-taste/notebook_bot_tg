from __future__ import annotations

import asyncio
import html
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.config import Settings
from app.db import Database
from app.keyboards import (
    FOOD_BUTTON,
    LAST_BUTTON,
    TASKS_BUTTON,
    TODAY_BUTTON,
    UNDO_BUTTON,
    WORKOUT_BUTTON,
    main_keyboard,
)
from app.llm_parser import LLMParserError, OpenRouterParser


LOGGER = logging.getLogger(__name__)
MAX_MESSAGE_LENGTH = 3900


def create_router(
    database: Database,
    parser: OpenRouterParser,
    settings: Settings,
) -> Router:
    router = Router(name="notes")

    @router.message(CommandStart())
    async def start_handler(message: Message) -> None:
        await message.answer(
            "Я сохраняю личные текстовые заметки и разбираю их на задачи, "
            "тренировки, питание и обычные заметки.\n\n"
            "Просто отправь текст. Команды: /today, /tasks, /food, /workout, "
            "/last, /undo, /health.",
            reply_markup=main_keyboard(),
        )

    @router.message(Command("today"))
    async def today_handler(message: Message) -> None:
        await show_today(message, database, settings)

    @router.message(Command("tasks"))
    async def tasks_handler(message: Message) -> None:
        await show_tasks(message, database)

    @router.message(Command("food"))
    async def food_handler(message: Message) -> None:
        await show_items_for_today(
            message,
            database,
            settings,
            item_type="food_log",
            heading="Питание за сегодня",
        )

    @router.message(Command("workout"))
    async def workout_handler(message: Message) -> None:
        await show_items_for_today(
            message,
            database,
            settings,
            item_type="workout_log",
            heading="Тренировки за сегодня",
        )

    @router.message(Command("last"))
    async def last_handler(message: Message) -> None:
        await show_last(message, database)

    @router.message(Command("undo"))
    async def undo_handler(message: Message) -> None:
        await undo_last(message, database)

    @router.message(Command("health"))
    async def health_handler(message: Message) -> None:
        healthy = await asyncio.to_thread(database.health_check)
        await message.answer("OK: бот и SQLite работают." if healthy else "Ошибка SQLite.")

    button_handlers: dict[str, Callable[[Message], Awaitable[None]]] = {
        TODAY_BUTTON: today_handler,
        TASKS_BUTTON: tasks_handler,
        FOOD_BUTTON: food_handler,
        WORKOUT_BUTTON: workout_handler,
        LAST_BUTTON: last_handler,
        UNDO_BUTTON: undo_handler,
    }

    @router.message(F.text)
    async def text_note_handler(message: Message) -> None:
        text = (message.text or "").strip()
        if not text:
            return

        button_handler = button_handlers.get(text)
        if button_handler:
            await button_handler(message)
            return

        if text.startswith("/"):
            await message.answer("Неизвестная команда. Используй /start.")
            return

        if message.from_user is None:
            await message.answer("Не удалось определить пользователя.")
            return

        try:
            parsed_note = await parser.parse(text)
            await asyncio.to_thread(
                database.save_note,
                message.from_user.id,
                text,
                parsed_note,
            )
        except LLMParserError:
            LOGGER.exception("LLM parsing failed for user_id=%s", message.from_user.id)
            await message.answer(
                "Не получилось разобрать заметку. Попробуй ещё раз немного позже."
            )
            return
        except Exception:
            LOGGER.exception("Saving note failed for user_id=%s", message.from_user.id)
            await message.answer("Не получилось сохранить заметку.")
            return

        await message.answer(html.escape(parsed_note.bot_reply))

    return router


async def show_today(
    message: Message,
    database: Database,
    settings: Settings,
) -> None:
    user_id = _user_id(message)
    if user_id is None:
        return

    local_date, start_utc, end_utc = local_day_bounds(settings.user_timezone)
    rows = await asyncio.to_thread(
        database.get_notes_between,
        user_id,
        start_utc,
        end_utc,
    )
    if not rows:
        await message.answer(f"За {local_date} записей нет.")
        return

    lines = [f"Записи за {local_date}:"]
    for index, row in enumerate(reversed(rows), start=1):
        parsed = _json_object(row["parsed_json"])
        reply = parsed.get("bot_reply") or shorten(row["raw_text"], 120)
        lines.append(f"{index}. {html.escape(str(reply))}")
    await message.answer(limit_message("\n".join(lines)))


async def show_tasks(message: Message, database: Database) -> None:
    user_id = _user_id(message)
    if user_id is None:
        return

    tasks = await asyncio.to_thread(database.get_active_tasks, user_id)
    if not tasks:
        await message.answer("Активных задач нет.")
        return

    lines = ["Активные задачи:"]
    for index, task in enumerate(tasks, start=1):
        lines.append(
            f"{index}. {html.escape(task['title'])} — {_format_due(task)}"
        )
    await message.answer(limit_message("\n".join(lines)))


async def show_items_for_today(
    message: Message,
    database: Database,
    settings: Settings,
    *,
    item_type: str,
    heading: str,
) -> None:
    user_id = _user_id(message)
    if user_id is None:
        return

    local_date, start_utc, end_utc = local_day_bounds(settings.user_timezone)
    items = await asyncio.to_thread(
        database.get_items_for_day,
        user_id,
        item_type,
        local_date,
        start_utc,
        end_utc,
    )
    if not items:
        await message.answer(f"{heading}: записей нет.")
        return

    lines = [f"{heading}:"]
    for index, item in enumerate(reversed(items), start=1):
        details = _format_data_json(item["data_json"])
        suffix = f" — {html.escape(details)}" if details else ""
        lines.append(f"{index}. {html.escape(item['title'])}{suffix}")
    await message.answer(limit_message("\n".join(lines)))


async def show_last(message: Message, database: Database) -> None:
    user_id = _user_id(message)
    if user_id is None:
        return

    row = await asyncio.to_thread(database.get_last_note, user_id)
    if row is None:
        await message.answer("Сохранённых заметок пока нет.")
        return

    parsed = _json_object(row["parsed_json"])
    bot_reply = parsed.get("bot_reply") or "Без краткого описания"
    await message.answer(
        limit_message(
            "Последняя заметка:\n"
            f"{html.escape(row['raw_text'])}\n\n"
            f"{html.escape(str(bot_reply))}"
        )
    )


async def undo_last(message: Message, database: Database) -> None:
    user_id = _user_id(message)
    if user_id is None:
        return

    deleted = await asyncio.to_thread(database.undo_last_note, user_id)
    if deleted is None:
        await message.answer("Удалять нечего.")
        return

    await message.answer(
        f"Удалил последнюю заметку: {html.escape(shorten(deleted['raw_text'], 150))}"
    )


def local_day_bounds(timezone_name: str) -> tuple[str, str, str]:
    try:
        tzinfo = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"Unknown timezone: {timezone_name}") from exc

    now = datetime.now(tzinfo)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return (
        start.date().isoformat(),
        start.astimezone(timezone.utc).isoformat(timespec="seconds"),
        end.astimezone(timezone.utc).isoformat(timespec="seconds"),
    )


def _user_id(message: Message) -> int | None:
    if message.from_user is None:
        return None
    return message.from_user.id


def _format_due(task: dict[str, Any]) -> str:
    labels = {
        "today": "сегодня",
        "tomorrow": "завтра",
        "this_week": "на этой неделе",
        "no_deadline": "без срока",
        "unknown": "срок неясен",
    }
    due_type = task.get("due_type")
    if due_type == "specific_date" and task.get("due_date"):
        return str(task["due_date"])
    return labels.get(due_type, "без срока")


def _format_data_json(data_json: str) -> str:
    data = _json_object(data_json)
    if not data:
        return ""
    return shorten(json.dumps(data, ensure_ascii=False), 180)


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def shorten(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def limit_message(value: str) -> str:
    return value if len(value) <= MAX_MESSAGE_LENGTH else value[:MAX_MESSAGE_LENGTH] + "…"
