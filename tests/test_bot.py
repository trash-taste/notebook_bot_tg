from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.telegram_bot.bot import (
    EDITING_TASK_ID_KEY,
    MENU_FOOD,
    MENU_NOTES,
    MENU_PROGRESS,
    MENU_TASKS,
    MENU_TODAY,
    MENU_WORKOUTS,
    USER_ERROR_REPLY,
    VOICE_ERROR_REPLY,
    build_main_menu_keyboard,
    build_note_record,
    handle_task_callback,
    tasks_command,
    handle_voice_message,
    handle_text_message,
    menu_command,
    progress_command,
    recent_items,
    shorten,
    start,
)
from src.voice_note_parser.openrouter import OpenRouterError
from tests.test_service import test_settings
from tests.test_validate import valid_payload


class FakeMessage:
    def __init__(self, text: str = "завтра купить магний", voice: object = None) -> None:
        self.text = text
        self.voice = voice
        self.message_id = 123
        self.replies: list[str] = []
        self.reply_markups: list[object] = []
        self.edits: list[str] = []
        self.edit_markups: list[object] = []

    async def reply_text(self, text: str, reply_markup: object = None) -> None:
        self.replies.append(text)
        self.reply_markups.append(reply_markup)

    async def edit_text(self, text: str, reply_markup: object = None) -> None:
        self.edits.append(text)
        self.edit_markups.append(reply_markup)


def fake_update(text: str = "завтра купить магний") -> SimpleNamespace:
    message = FakeMessage(text)
    return SimpleNamespace(
        message=message,
        effective_message=message,
        effective_chat=SimpleNamespace(id=10),
        effective_user=SimpleNamespace(id=20),
    )


def fake_voice_update() -> SimpleNamespace:
    voice = SimpleNamespace(file_id="voice-file-id", duration=7)
    message = FakeMessage(text="", voice=voice)
    return SimpleNamespace(
        message=message,
        effective_message=message,
        effective_chat=SimpleNamespace(id=10),
        effective_user=SimpleNamespace(id=20),
    )


class FakeCallbackQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = FakeMessage()
        self.answered = False

    async def answer(self) -> None:
        self.answered = True


def fake_callback_update(data: str) -> SimpleNamespace:
    query = FakeCallbackQuery(data)
    return SimpleNamespace(
        callback_query=query,
        effective_chat=SimpleNamespace(id=10),
        effective_user=SimpleNamespace(id=20),
    )


def active_task(task_id: str = "task-1", title: str = "Купить магний") -> dict:
    return {
        "task_id": task_id,
        "chat_id": 10,
        "user_id": 20,
        "title": title,
        "due_type": "tomorrow",
        "due_date": "2026-06-10",
        "priority": "normal",
        "status": "active",
        "created_at": "2026-06-09T10:00:00+00:00",
        "updated_at": "2026-06-09T10:00:00+00:00",
        "source_message_id": 123,
    }


class BotTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_replies_with_short_intro(self) -> None:
        update = fake_update()
        await start(update, SimpleNamespace())

        self.assertIn("Главное меню", update.message.replies[0])
        self.assertIsNotNone(update.message.reply_markups[0])

    async def test_menu_command_shows_main_menu(self) -> None:
        update = fake_update()
        await menu_command(update, SimpleNamespace())

        self.assertEqual(update.message.replies, ["Главное меню\nЧто показать?"])
        self.assertIsNotNone(update.message.reply_markups[0])

    async def test_handle_text_message_replies_and_saves_record(self) -> None:
        update = fake_update()
        context = SimpleNamespace(bot_data={"settings": test_settings()}, user_data={})
        payload = valid_payload()

        with (
            patch("src.telegram_bot.bot.parse_transcript", return_value=payload) as parse,
            patch("src.telegram_bot.bot.append_note_record") as append,
            patch("src.telegram_bot.bot.save_tasks_from_parser_result") as save_tasks,
        ):
            await handle_text_message(update, context)

        parse.assert_called_once()
        append.assert_called_once()
        save_tasks.assert_called_once_with(update, payload)
        self.assertEqual(update.message.replies, [payload["bot_reply"]])
        saved_record = append.call_args.args[0]
        self.assertEqual(saved_record["chat_id"], 10)
        self.assertEqual(saved_record["user_id"], 20)
        self.assertEqual(saved_record["message_id"], 123)
        self.assertEqual(saved_record["raw_text"], "завтра купить магний")
        self.assertEqual(saved_record["parser_result"], payload)

    async def test_handle_text_message_returns_safe_error(self) -> None:
        update = fake_update()
        context = SimpleNamespace(bot_data={"settings": test_settings()}, user_data={})

        with (
            patch(
                "src.telegram_bot.bot.parse_transcript",
                side_effect=OpenRouterError("boom"),
            ),
            patch("src.telegram_bot.bot.LOGGER.exception"),
        ):
            await handle_text_message(update, context)

        self.assertEqual(update.message.replies, [USER_ERROR_REPLY])

    async def test_handle_text_message_routes_main_menu_button_without_parser(self) -> None:
        update = fake_update(MENU_TASKS)
        context = SimpleNamespace(bot_data={"settings": test_settings()}, user_data={})

        with (
            patch("src.telegram_bot.bot.active_tasks_for_chat", return_value=[]),
            patch("src.telegram_bot.bot.parse_transcript") as parse,
        ):
            await handle_text_message(update, context)

        parse.assert_not_called()
        self.assertEqual(update.message.replies, ["Активных задач нет."])

    async def test_handle_text_message_edit_mode_renames_task_without_parser(self) -> None:
        update = fake_update("Купить магний и цинк")
        context = SimpleNamespace(
            bot_data={"settings": test_settings()},
            user_data={EDITING_TASK_ID_KEY: "task-1"},
        )

        with (
            patch("src.telegram_bot.bot.rename_task", return_value=active_task(title="Купить магний и цинк")) as rename,
            patch("src.telegram_bot.bot.active_tasks_for_chat", return_value=[active_task(title="Купить магний и цинк")]),
            patch("src.telegram_bot.bot.parse_transcript") as parse,
        ):
            await handle_text_message(update, context)

        rename.assert_called_once_with("task-1", "Купить магний и цинк")
        parse.assert_not_called()
        self.assertNotIn(EDITING_TASK_ID_KEY, context.user_data)
        self.assertIn("Изменил задачу", update.message.replies[0])
        self.assertIn("Активные задачи:", update.message.replies[1])

    async def test_tasks_command_shows_active_tasks_with_keyboard(self) -> None:
        update = fake_update()
        context = SimpleNamespace()

        with patch("src.telegram_bot.bot.active_tasks_for_chat", return_value=[active_task()]) as active:
            await tasks_command(update, context)

        active.assert_called_once_with(10)
        self.assertIn("Активные задачи:", update.message.replies[0])
        self.assertIn("1. Купить магний — завтра", update.message.replies[0])
        self.assertIsNotNone(update.message.reply_markups[0])

    async def test_tasks_command_handles_empty_list(self) -> None:
        update = fake_update()
        context = SimpleNamespace()

        with patch("src.telegram_bot.bot.active_tasks_for_chat", return_value=[]):
            await tasks_command(update, context)

        self.assertEqual(update.message.replies, ["Активных задач нет."])
        self.assertEqual(update.message.reply_markups, [None])

    async def test_today_menu_shows_today_tasks(self) -> None:
        update = fake_update(MENU_TODAY)
        context = SimpleNamespace(bot_data={"settings": test_settings()}, user_data={})
        today_task = active_task(title="Оплатить аренду")
        today_task["due_type"] = "today"

        with patch("src.telegram_bot.bot.active_tasks_for_chat", return_value=[today_task]):
            await handle_text_message(update, context)

        self.assertEqual(update.message.replies, ["Сегодня:\n1. Оплатить аренду"])

    async def test_recent_menu_buttons_show_items(self) -> None:
        update = fake_update(MENU_FOOD)
        context = SimpleNamespace(bot_data={"settings": test_settings()}, user_data={})
        payload = valid_payload()
        payload["items"] = [
            {
                "type": "food_log",
                "category": "food",
                "title": "Гречка",
                "date": "2026-06-09",
                "due_type": None,
                "due_date": None,
                "priority": None,
                "status": None,
                "data": {},
                "raw_fragment": "ел гречку",
                "missing_fields": [],
                "confidence": 0.8,
                "needs_clarification": False,
            }
        ]

        with patch(
            "src.telegram_bot.bot.read_note_records",
            return_value=[{"chat_id": 10, "parser_result": payload}],
        ):
            await handle_text_message(update, context)

        self.assertEqual(update.message.replies, ["Последнее питание:\n1. Гречка"])

    async def test_progress_button_shows_counts(self) -> None:
        update = fake_update(MENU_PROGRESS)
        context = SimpleNamespace(bot_data={"settings": test_settings()}, user_data={})

        with (
            patch(
                "src.telegram_bot.bot.read_note_records",
                return_value=[{"chat_id": 10, "parser_result": valid_payload()}],
            ),
            patch(
                "src.telegram_bot.bot.read_task_records",
                return_value=[active_task(), {**active_task("task-2"), "status": "done"}],
            ),
        ):
            await handle_text_message(update, context)

        self.assertIn("Прогресс:", update.message.replies[0])
        self.assertIn("Активные задачи: 1", update.message.replies[0])
        self.assertIn("Выполнено задач: 1", update.message.replies[0])

    async def test_notes_button_shows_recent_notes(self) -> None:
        update = fake_update(MENU_NOTES)
        context = SimpleNamespace(bot_data={"settings": test_settings()}, user_data={})

        with patch(
            "src.telegram_bot.bot.read_note_records",
            return_value=[{"chat_id": 10, "raw_text": "первая заметка"}],
        ):
            await handle_text_message(update, context)

        self.assertEqual(update.message.replies, ["Последние заметки:\n1. первая заметка"])

    async def test_done_callback_marks_task_done_and_refreshes_list(self) -> None:
        update = fake_callback_update("task:done:task-1")
        context = SimpleNamespace(bot_data={"settings": test_settings()}, user_data={})

        with (
            patch("src.telegram_bot.bot.mark_task_done", return_value=active_task()) as done,
            patch("src.telegram_bot.bot.active_tasks_for_chat", return_value=[]),
        ):
            await handle_task_callback(update, context)

        self.assertTrue(update.callback_query.answered)
        done.assert_called_once_with("task-1")
        self.assertEqual(update.callback_query.message.edits, ["Активных задач нет."])

    async def test_reschedule_callback_shows_quick_due_options(self) -> None:
        update = fake_callback_update("task:reschedule:task-1")
        context = SimpleNamespace(bot_data={"settings": test_settings()}, user_data={})

        await handle_task_callback(update, context)

        self.assertEqual(update.callback_query.message.edits, ["Куда перенести задачу?"])
        self.assertIsNotNone(update.callback_query.message.edit_markups[0])

    async def test_due_callback_updates_due_and_refreshes_list(self) -> None:
        update = fake_callback_update("task:due:task-1:tomorrow")
        context = SimpleNamespace(bot_data={"settings": test_settings()}, user_data={})

        with (
            patch("src.telegram_bot.bot.reschedule_task", return_value=active_task()) as reschedule,
            patch("src.telegram_bot.bot.active_tasks_for_chat", return_value=[active_task()]),
        ):
            await handle_task_callback(update, context)

        reschedule.assert_called_once_with(
            "task-1",
            "tomorrow",
            user_timezone="Asia/Almaty",
        )
        self.assertIn("Активные задачи:", update.callback_query.message.edits[0])

    async def test_edit_callback_sets_editing_state(self) -> None:
        update = fake_callback_update("task:edit:task-1")
        context = SimpleNamespace(bot_data={"settings": test_settings()}, user_data={})

        with patch("src.telegram_bot.bot.get_task", return_value=active_task()) as get:
            await handle_task_callback(update, context)

        get.assert_called_once_with("task-1")
        self.assertEqual(context.user_data[EDITING_TASK_ID_KEY], "task-1")
        self.assertEqual(
            update.callback_query.message.edits,
            ["Отправь новое название задачи одним сообщением."],
        )

    async def test_handle_voice_message_transcribes_parses_replies_and_saves(self) -> None:
        update = fake_voice_update()
        context = SimpleNamespace(bot_data={"settings": test_settings()}, user_data={})

        with patch("src.telegram_bot.bot.parse_transcript") as parse:
            await handle_voice_message(update, context)

        parse.assert_not_called()
        self.assertEqual(update.message.replies, [VOICE_ERROR_REPLY])
        self.assertIsNotNone(update.message.reply_markups[0])

    def test_build_note_record_uses_telegram_metadata(self) -> None:
        update = fake_update("текст")
        record = build_note_record(update, "текст", {"bot_reply": "ok"})

        self.assertEqual(record["chat_id"], 10)
        self.assertEqual(record["user_id"], 20)
        self.assertEqual(record["message_id"], 123)
        self.assertEqual(record["raw_text"], "текст")
        self.assertEqual(record["parser_result"], {"bot_reply": "ok"})

    def test_build_note_record_accepts_voice_metadata(self) -> None:
        update = fake_voice_update()
        record = build_note_record(
            update,
            "транскрипт",
            {"bot_reply": "ok"},
            source="voice",
            extra={
                "transcript": "транскрипт",
                "voice_file_id": "voice-file-id",
                "duration": 7,
            },
        )

        self.assertEqual(record["source"], "voice")
        self.assertEqual(record["raw_text"], "транскрипт")
        self.assertEqual(record["transcript"], "транскрипт")
        self.assertEqual(record["voice_file_id"], "voice-file-id")
        self.assertEqual(record["duration"], 7)

    def test_build_main_menu_keyboard(self) -> None:
        keyboard = build_main_menu_keyboard()
        self.assertIsNotNone(keyboard)

    def test_recent_items_filters_by_chat_and_type(self) -> None:
        payload = valid_payload()
        records = [
            {"chat_id": 999, "parser_result": payload},
            {"chat_id": 10, "parser_result": payload},
        ]

        items = recent_items(records, chat_id=10, item_type="task", limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Купить магний")

    def test_shorten_compacts_long_text(self) -> None:
        self.assertEqual(shorten("  коротко   тут ", limit=20), "коротко тут")
        self.assertEqual(shorten("очень длинный текст", limit=8), "очень…")


if __name__ == "__main__":
    unittest.main()
