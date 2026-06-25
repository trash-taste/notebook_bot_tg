from __future__ import annotations

import asyncio
import html
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.config import Settings
from app.context import BotContext, collect_context, context_to_text, day_bounds_for_date
from app.db import Database
from app.intent_parser import IntentParser
from app.keyboards import (
    FOOD_BUTTON,
    LAST_BUTTON,
    TASKS_BUTTON,
    TODAY_BUTTON,
    UNDO_BUTTON,
    WORKOUT_BUTTON,
    clarification_keyboard,
    delete_confirmation_keyboard,
    main_keyboard,
    reschedule_keyboard,
    tasks_keyboard,
)
from app.llm_parser import LLMParserError, OpenRouterParser
from app.models import IntentResult
from app.obsidian import ObsidianExporter


LOGGER = logging.getLogger(__name__)
MAX_MESSAGE_LENGTH = 3900


class TaskEdit(StatesGroup):
    waiting_for_title = State()


class Clarification(StatesGroup):
    waiting_for_target = State()


def create_router(
    database: Database,
    parser: OpenRouterParser,
    settings: Settings,
) -> Router:
    router = Router(name="notes")
    obsidian_exporter = ObsidianExporter(
        settings.obsidian_vault_path,
        enabled=settings.enable_obsidian_export,
    )
    intent_parser = IntentParser(settings)

    @router.message(CommandStart())
    async def start_handler(message: Message) -> None:
        await message.answer(
            "Я сохраняю личные текстовые заметки и разбираю их на задачи, "
            "тренировки, питание и обычные заметки.\n\n"
            "Просто отправь текст. Команды: /today, /tasks, /food, /workout, "
            "/last, /undo, /context, /export_today, /rebuild_today, /health.",
            reply_markup=main_keyboard(),
        )

    @router.message(Command("today"))
    async def today_handler(message: Message) -> None:
        await show_today(message, database, settings)

    @router.message(Command("tasks"))
    async def tasks_handler(message: Message) -> None:
        await show_tasks(message, database)

    @router.message(Command("cancel"))
    async def cancel_handler(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("Редактирование отменено.")

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

    @router.message(Command("context"))
    async def context_handler(message: Message) -> None:
        user_id = _user_id(message)
        if user_id is None:
            return
        context = await asyncio.to_thread(
            collect_context,
            database,
            user_id=user_id,
            timezone_name=settings.user_timezone,
            user_text="",
            obsidian_vault_path=settings.obsidian_vault_path,
        )
        await message.answer(limit_message(html.escape(context_to_text(context))))

    @router.message(Command("rebuild_today"))
    async def rebuild_today_handler(message: Message) -> None:
        await rebuild_today(message, database, settings, obsidian_exporter)

    @router.message(Command("export_today"))
    async def export_today_handler(message: Message) -> None:
        await export_today(message, database, settings, obsidian_exporter)

    button_handlers: dict[str, Callable[[Message], Awaitable[None]]] = {
        TODAY_BUTTON: today_handler,
        TASKS_BUTTON: tasks_handler,
        FOOD_BUTTON: food_handler,
        WORKOUT_BUTTON: workout_handler,
        LAST_BUTTON: last_handler,
        UNDO_BUTTON: undo_handler,
    }

    @router.callback_query(F.data.startswith("task:"))
    async def task_callback_handler(
        query: CallbackQuery,
        state: FSMContext,
    ) -> None:
        await handle_task_callback(
            query,
            state,
            database,
            settings,
            obsidian_exporter,
        )

    @router.callback_query(F.data.startswith("clarify:"))
    async def clarification_callback_handler(
        query: CallbackQuery,
        state: FSMContext,
    ) -> None:
        await handle_clarification_callback(
            query,
            state,
            database,
            parser,
            settings,
            obsidian_exporter,
        )

    @router.message(TaskEdit.waiting_for_title, F.text)
    async def task_title_handler(message: Message, state: FSMContext) -> None:
        user_id = _user_id(message)
        if user_id is None:
            return

        title = " ".join((message.text or "").split())
        if not title:
            await message.answer("Название не может быть пустым.")
            return
        if len(title) > 300:
            await message.answer("Название слишком длинное. Максимум 300 символов.")
            return

        state_data = await state.get_data()
        task_id = state_data.get("task_id")
        updated = await asyncio.to_thread(
            database.rename_task,
            user_id,
            task_id,
            title,
        )
        await state.clear()
        if not updated:
            await message.answer("Задача не найдена.")
            return

        await rebuild_daily_notes(
            database,
            settings,
            obsidian_exporter,
            user_id,
            [_today(settings.user_timezone)],
        )
        await message.answer(f"Изменил задачу: {html.escape(title)}")
        await show_tasks(message, database)

    @router.message(F.text)
    async def text_note_handler(message: Message, state: FSMContext) -> None:
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

        await process_user_text(
            message,
            database=database,
            parser=parser,
            intent_parser=intent_parser,
            settings=settings,
            obsidian_exporter=obsidian_exporter,
            text=text,
            state=state,
        )

    return router


async def process_user_text(
    message: Message,
    *,
    database: Database,
    parser: OpenRouterParser,
    intent_parser: IntentParser,
    settings: Settings,
    obsidian_exporter: ObsidianExporter,
    text: str,
    state: FSMContext,
) -> None:
    user_id = _user_id(message)
    if user_id is None:
        return

    context = await asyncio.to_thread(
        collect_context,
        database,
        user_id=user_id,
        timezone_name=settings.user_timezone,
        user_text=text,
        obsidian_vault_path=settings.obsidian_vault_path,
    )

    try:
        intent = await intent_parser.detect(text, context)
    except LLMParserError:
        LOGGER.exception("Intent detection failed for user_id=%s", user_id)
        intent = IntentResult(
            intent="create_new_item",
            target_type=context.preferred_type,  # type: ignore[arg-type]
            target_item_id=None,
            target_date=context.current_date,
            action=None,
            data={},
            confidence=0.76,
            needs_clarification=False,
            clarification_question=None,
            candidate_item_ids=[],
        )

    intent = _resolve_obvious_target(intent, context)

    if _should_ask_clarification(intent):
        await ask_clarification(message, state, database, user_id, text, intent, context)
        return

    if intent.intent == "create_new_item":
        await create_new_item(
            message,
            database,
            parser,
            settings,
            obsidian_exporter,
            text,
            context.current_date,
        )
        return

    if intent.intent == "append_to_existing_item":
        await append_to_existing_item(
            message,
            database,
            settings,
            obsidian_exporter,
            text,
            intent,
            context,
        )
        return

    if intent.intent == "update_existing_item":
        await update_existing_item(
            message,
            database,
            settings,
            obsidian_exporter,
            text,
            intent,
            context,
        )
        return

    if intent.intent == "archive_item":
        await archive_existing_item(
            message,
            database,
            settings,
            obsidian_exporter,
            text,
            intent,
            context,
        )
        return

    if intent.intent == "query_items":
        await answer_query(message, database, settings, intent, context)
        return

    await ask_clarification(message, state, database, user_id, text, intent, context)


async def create_new_item(
    message: Message,
    database: Database,
    parser: OpenRouterParser,
    settings: Settings,
    obsidian_exporter: ObsidianExporter,
    text: str,
    current_date: str,
    *,
    user_id_override: int | None = None,
) -> None:
    user_id = user_id_override or _user_id(message)
    if user_id is None:
        return
    try:
        parsed_note = await parser.parse(text)
        note_id = await asyncio.to_thread(
            database.save_note,
            user_id,
            text,
            parsed_note,
        )
        note_items = await asyncio.to_thread(database.get_items_for_note, user_id, note_id)
        dates = _dates_for_items(note_items, fallback=current_date)
        await rebuild_daily_notes(database, settings, obsidian_exporter, user_id, dates)
    except LLMParserError:
        LOGGER.exception("LLM parsing failed for user_id=%s", user_id)
        await message.answer("Не получилось разобрать заметку. Попробуй ещё раз позже.")
        return
    except OSError:
        LOGGER.exception("Obsidian export failed for user_id=%s", user_id)
        await message.answer("Заметку сохранил, но не получилось обновить Obsidian.")
        return
    except Exception:
        LOGGER.exception("Saving note failed for user_id=%s", user_id)
        await message.answer("Не получилось сохранить заметку.")
        return

    await message.answer(html.escape(parsed_note.bot_reply))


async def append_to_existing_item(
    message: Message,
    database: Database,
    settings: Settings,
    obsidian_exporter: ObsidianExporter,
    text: str,
    intent: IntentResult,
    context: BotContext,
    *,
    user_id_override: int | None = None,
) -> None:
    user_id = user_id_override or _user_id(message)
    if user_id is None or intent.target_item_id is None:
        return
    item = await asyncio.to_thread(database.get_item, user_id, intent.target_item_id)
    if item is None:
        await message.answer("Не нашёл запись, которую нужно дополнить.")
        return

    data = intent.data or _fallback_append_data(text, item["type"])
    updated = await asyncio.to_thread(
        database.append_item_data,
        user_id,
        intent.target_item_id,
        data,
        raw_text=text,
    )
    if not updated:
        await message.answer("Не получилось дополнить запись.")
        return

    dates = _dates_for_items([item], fallback=context.current_date)
    await rebuild_daily_notes(database, settings, obsidian_exporter, user_id, dates)
    await message.answer(f"Добавил к записи: {html.escape(item['title'])}")


async def update_existing_item(
    message: Message,
    database: Database,
    settings: Settings,
    obsidian_exporter: ObsidianExporter,
    text: str,
    intent: IntentResult,
    context: BotContext,
) -> None:
    user_id = _user_id(message)
    if user_id is None or intent.target_item_id is None:
        return
    item = await asyncio.to_thread(database.get_item, user_id, intent.target_item_id)
    if item is None:
        await message.answer("Не нашёл запись, которую нужно изменить.")
        return

    fields = {
        key: value
        for key, value in intent.data.items()
        if key in {"title", "date", "due_type", "due_date", "priority", "status", "data"}
    }
    if not fields:
        await message.answer("Понял изменение, но не понял какие поля обновить.")
        return
    updated = await asyncio.to_thread(
        database.update_item,
        user_id,
        intent.target_item_id,
        fields,
        raw_text=text,
    )
    if not updated:
        await message.answer("Не получилось обновить запись.")
        return

    dates = _dates_for_items([item, {**item, **fields}], fallback=context.current_date)
    await rebuild_daily_notes(database, settings, obsidian_exporter, user_id, dates)
    await message.answer(f"Обновил запись: {html.escape(item['title'])}")


async def archive_existing_item(
    message: Message,
    database: Database,
    settings: Settings,
    obsidian_exporter: ObsidianExporter,
    text: str,
    intent: IntentResult,
    context: BotContext,
) -> None:
    user_id = _user_id(message)
    if user_id is None:
        return

    if intent.target_item_id is None:
        archived = await asyncio.to_thread(database.undo_last_note, user_id)
        if archived is None:
            await message.answer("Архивировать нечего.")
            return
        await rebuild_daily_notes(
            database,
            settings,
            obsidian_exporter,
            user_id,
            [context.current_date],
        )
        await message.answer(
            f"Архивировал последнюю запись: {html.escape(shorten(archived['raw_text'], 150))}"
        )
        return

    item = await asyncio.to_thread(database.get_item, user_id, intent.target_item_id)
    updated = await asyncio.to_thread(
        database.archive_item,
        user_id,
        intent.target_item_id,
        raw_text=text,
    )
    if not updated:
        await message.answer("Не получилось архивировать запись.")
        return

    dates = _dates_for_items([item] if item else [], fallback=context.current_date)
    await rebuild_daily_notes(database, settings, obsidian_exporter, user_id, dates)
    await message.answer("Запись архивирована.")


async def answer_query(
    message: Message,
    database: Database,
    settings: Settings,
    intent: IntentResult,
    context: BotContext,
) -> None:
    target = intent.target_type or context.preferred_type
    action = intent.action or ""
    if target == "food_log" or "food" in action:
        await show_items_for_today(
            message,
            database,
            settings,
            item_type="food_log",
            heading="Питание за сегодня",
        )
        return
    if target == "workout_log" or "workout" in action:
        await show_items_for_today(
            message,
            database,
            settings,
            item_type="workout_log",
            heading="Тренировки за сегодня",
        )
        return
    if target == "task" or "task" in action:
        await show_tasks(message, database)
        return
    await show_today(message, database, settings)


async def ask_clarification(
    message: Message,
    state: FSMContext,
    database: Database,
    user_id: int,
    text: str,
    intent: IntentResult,
    context: BotContext,
) -> None:
    candidates = await _candidate_items(database, user_id, intent, context)
    await state.set_state(Clarification.waiting_for_target)
    await state.update_data(
        pending_text=text,
        pending_intent=intent.model_dump(mode="json"),
    )
    question = intent.clarification_question or "Куда добавить это?"
    await message.answer(
        html.escape(question),
        reply_markup=clarification_keyboard(candidates),
    )


async def handle_clarification_callback(
    query: CallbackQuery,
    state: FSMContext,
    database: Database,
    parser: OpenRouterParser,
    settings: Settings,
    obsidian_exporter: ObsidianExporter,
) -> None:
    data = query.data or ""
    parts = data.split(":")
    if len(parts) != 3:
        await query.answer("Некорректная кнопка.", show_alert=True)
        return
    action = parts[1]
    state_data = await state.get_data()
    text = state_data.get("pending_text")
    intent_data = state_data.get("pending_intent")
    if not isinstance(text, str) or not isinstance(intent_data, dict):
        await state.clear()
        await query.answer("Контекст устарел.", show_alert=True)
        return

    pseudo_message = query.message
    if pseudo_message is None:
        await state.clear()
        await query.answer("Сообщение недоступно.", show_alert=True)
        return

    if action == "cancel":
        await state.clear()
        await query.answer("Отменено")
        await pseudo_message.answer("Ок, ничего не меняю.")
        return

    if action == "new":
        await state.clear()
        await query.answer("Создаю новую запись")
        await create_new_item(
            pseudo_message,
            database,
            parser,
            settings,
            obsidian_exporter,
            text,
            _today(settings.user_timezone),
            user_id_override=query.from_user.id,
        )
        return

    if action != "item":
        await query.answer("Некорректное действие.", show_alert=True)
        return

    try:
        item_id = int(parts[2])
    except ValueError:
        await query.answer("Некорректная запись.", show_alert=True)
        return

    user_id = query.from_user.id
    item = await asyncio.to_thread(database.get_item, user_id, item_id)
    if item is None:
        await state.clear()
        await query.answer("Запись не найдена.", show_alert=True)
        return

    intent = IntentResult.model_validate(intent_data).model_copy(
        update={
            "intent": "append_to_existing_item",
            "target_item_id": item_id,
            "target_type": item["type"],
            "confidence": 0.9,
            "needs_clarification": False,
        }
    )
    await state.clear()
    await query.answer("Добавляю")
    context = await asyncio.to_thread(
        collect_context,
        database,
        user_id=user_id,
        timezone_name=settings.user_timezone,
        user_text=text,
        obsidian_vault_path=settings.obsidian_vault_path,
    )
    await append_to_existing_item(
        pseudo_message,
        database,
        settings,
        obsidian_exporter,
        text,
        intent,
        context,
        user_id_override=query.from_user.id,
    )


async def rebuild_daily_notes(
    database: Database,
    settings: Settings,
    obsidian_exporter: ObsidianExporter,
    user_id: int,
    dates: list[str],
) -> None:
    for local_date in sorted(set(dates)):
        _, start_utc, end_utc = day_bounds_for_date(local_date, settings.user_timezone)
        items = await asyncio.to_thread(
            database.get_items_for_local_date,
            user_id,
            local_date,
            start_utc,
            end_utc,
        )
        await asyncio.to_thread(
            obsidian_exporter.rebuild_daily_note,
            user_id=user_id,
            date=local_date,
            items=items,
        )


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
    await message.answer(
        limit_message("\n".join(lines)),
        reply_markup=tasks_keyboard(tasks),
    )


async def handle_task_callback(
    query: CallbackQuery,
    state: FSMContext,
    database: Database,
    settings: Settings,
    obsidian_exporter: ObsidianExporter,
) -> None:
    user_id = query.from_user.id
    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        await query.answer("Некорректная кнопка.", show_alert=True)
        return

    action = parts[1]
    try:
        task_id = int(parts[2])
    except ValueError:
        await query.answer("Некорректная задача.", show_alert=True)
        return

    if action == "cancel":
        await state.clear()
        await query.answer("Отменено")
        await refresh_tasks_message(query, database)
        return

    task = await asyncio.to_thread(database.get_task, user_id, task_id)
    if task is None:
        await query.answer("Задача не найдена.", show_alert=True)
        await refresh_tasks_message(query, database)
        return

    if action == "done":
        await asyncio.to_thread(database.complete_task, user_id, task_id)
        await rebuild_daily_notes(
            database,
            settings,
            obsidian_exporter,
            user_id,
            _dates_for_items([task], fallback=_today(settings.user_timezone)),
        )
        await query.answer("Задача выполнена")
        await refresh_tasks_message(query, database)
        return

    if action == "edit":
        await state.set_state(TaskEdit.waiting_for_title)
        await state.update_data(task_id=task_id)
        await query.answer()
        if query.message:
            await query.message.answer(
                "Отправь новое название задачи одним сообщением.\n"
                "Для отмены: /cancel"
            )
        return

    if action == "move":
        await query.answer()
        if query.message:
            await query.message.edit_text(
                f"Куда перенести задачу «{html.escape(task['title'])}»?",
                reply_markup=reschedule_keyboard(task_id),
            )
        return

    if action == "due" and len(parts) == 4:
        due_type = parts[3]
        due_date = due_date_for_type(due_type, settings.user_timezone)
        updated = await asyncio.to_thread(
            database.reschedule_task,
            user_id,
            task_id,
            due_type,
            due_date,
        )
        await query.answer("Срок изменён" if updated else "Некорректный срок")
        await rebuild_daily_notes(
            database,
            settings,
            obsidian_exporter,
            user_id,
            _dates_for_items(
                [task, {**task, "due_type": due_type, "due_date": due_date}],
                fallback=_today(settings.user_timezone),
            ),
        )
        await refresh_tasks_message(query, database)
        return

    if action == "delete":
        await query.answer()
        if query.message:
            await query.message.edit_text(
                f"Удалить задачу «{html.escape(task['title'])}»?",
                reply_markup=delete_confirmation_keyboard(task_id),
            )
        return

    if action == "delete_yes":
        await asyncio.to_thread(database.delete_task, user_id, task_id)
        await rebuild_daily_notes(
            database,
            settings,
            obsidian_exporter,
            user_id,
            _dates_for_items([task], fallback=_today(settings.user_timezone)),
        )
        await query.answer("Задача удалена")
        await refresh_tasks_message(query, database)
        return

    await query.answer("Неизвестное действие.", show_alert=True)


async def refresh_tasks_message(query: CallbackQuery, database: Database) -> None:
    if query.message is None:
        return
    tasks = await asyncio.to_thread(database.get_active_tasks, query.from_user.id)
    if not tasks:
        await query.message.edit_text("Активных задач нет.")
        return

    lines = ["Активные задачи:"]
    for index, task in enumerate(tasks, start=1):
        lines.append(f"{index}. {html.escape(task['title'])} — {_format_due(task)}")
    await query.message.edit_text(
        limit_message("\n".join(lines)),
        reply_markup=tasks_keyboard(tasks),
    )


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

    archived = await asyncio.to_thread(database.undo_last_note, user_id)
    if archived is None:
        await message.answer("Удалять нечего.")
        return

    await rebuild_daily_notes(
        database,
        settings,
        ObsidianExporter(
            settings.obsidian_vault_path,
            enabled=settings.enable_obsidian_export,
        ),
        user_id,
        [_today(settings.user_timezone)],
    )
    await message.answer(
        f"Архивировал последнюю заметку: {html.escape(shorten(archived['raw_text'], 150))}"
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


def due_date_for_type(due_type: str, timezone_name: str) -> str | None:
    if due_type not in {"today", "tomorrow", "this_week", "no_deadline"}:
        return None
    try:
        tzinfo = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"Unknown timezone: {timezone_name}") from exc

    today = datetime.now(tzinfo).date()
    if due_type == "today":
        return today.isoformat()
    if due_type == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    return None


async def rebuild_today(
    message: Message,
    database: Database,
    settings: Settings,
    obsidian_exporter: ObsidianExporter,
) -> None:
    user_id = _user_id(message)
    if user_id is None:
        return
    today = _today(settings.user_timezone)
    await rebuild_daily_notes(database, settings, obsidian_exporter, user_id, [today])
    path = obsidian_exporter.daily_note_path(today)
    if path is None or not obsidian_exporter.enabled:
        await message.answer("Obsidian export выключен или путь не настроен.")
        return
    await message.answer(f"Daily note пересобран: {html.escape(str(path))}")


async def export_today(
    message: Message,
    database: Database,
    settings: Settings,
    obsidian_exporter: ObsidianExporter,
) -> None:
    user_id = _user_id(message)
    if user_id is None:
        return
    today = _today(settings.user_timezone)
    await rebuild_daily_notes(database, settings, obsidian_exporter, user_id, [today])
    path = obsidian_exporter.daily_note_path(today)
    if path is None or not path.exists():
        await message.answer("Markdown-файл за сегодня пока не создан.")
        return
    await message.answer_document(FSInputFile(path))


def _resolve_obvious_target(intent: IntentResult, context: BotContext) -> IntentResult:
    if intent.target_item_id is not None:
        return intent
    if intent.intent not in {"append_to_existing_item", "update_existing_item"}:
        return intent

    preferred = intent.target_type or context.preferred_type
    if preferred is None:
        return intent

    today_matches = [item for item in context.today_items if item.get("type") == preferred]
    if len(today_matches) == 1:
        return intent.model_copy(
            update={
                "target_type": preferred,
                "target_item_id": today_matches[0]["id"],
                "confidence": max(intent.confidence, 0.82),
                "needs_clarification": False,
            }
        )
    if preferred == "food_log" and context.last_food:
        return intent.model_copy(
            update={
                "target_type": preferred,
                "target_item_id": context.last_food["id"],
                "confidence": max(intent.confidence, 0.8),
                "needs_clarification": False,
            }
        )
    if preferred == "workout_log" and context.last_workout:
        return intent.model_copy(
            update={
                "target_type": preferred,
                "target_item_id": context.last_workout["id"],
                "confidence": max(intent.confidence, 0.8),
                "needs_clarification": False,
            }
        )
    if preferred == "task" and len(context.active_tasks) == 1:
        return intent.model_copy(
            update={
                "target_type": preferred,
                "target_item_id": context.active_tasks[0]["id"],
                "confidence": max(intent.confidence, 0.8),
                "needs_clarification": False,
            }
        )
    return intent


def _should_ask_clarification(intent: IntentResult) -> bool:
    if intent.intent == "create_new_item":
        return False
    if intent.needs_clarification or intent.intent == "clarification_needed":
        return True
    if intent.confidence < 0.75:
        return True
    if intent.intent in {"append_to_existing_item", "update_existing_item"}:
        return intent.target_item_id is None
    return False


async def _candidate_items(
    database: Database,
    user_id: int,
    intent: IntentResult,
    context: BotContext,
) -> list[dict[str, Any]]:
    candidates = await asyncio.to_thread(
        database.get_items_by_ids,
        user_id,
        intent.candidate_item_ids,
    )
    if candidates:
        return candidates
    preferred = intent.target_type or context.preferred_type
    if preferred:
        typed = [item for item in context.today_items if item.get("type") == preferred]
        if typed:
            return typed
    result = []
    for item in [context.last_food, context.last_workout, context.last_general_note]:
        if item and item not in result:
            result.append(item)
    result.extend(item for item in context.recent_items if item not in result)
    return result[:6]


def _fallback_append_data(text: str, item_type: str) -> dict[str, Any]:
    normalized = " ".join(text.split())
    if item_type == "food_log":
        return {"items": [{"name": normalized, "amount": None}]}
    if item_type == "workout_log":
        return {"exercises": [{"exercise": normalized}]}
    if item_type == "task":
        return {"notes": [normalized]}
    return {"notes": [normalized]}


def _dates_for_items(items: list[dict[str, Any]], *, fallback: str) -> list[str]:
    dates = {fallback}
    for item in items:
        if not item:
            continue
        for key in ("date", "due_date"):
            value = item.get(key)
            if isinstance(value, str) and value:
                dates.add(value)
    return sorted(dates)


def _today(timezone_name: str) -> str:
    try:
        tzinfo = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"Unknown timezone: {timezone_name}") from exc
    return datetime.now(tzinfo).date().isoformat()


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
