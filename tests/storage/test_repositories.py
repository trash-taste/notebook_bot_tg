from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from packages.storage.db import create_schema, create_sqlite_engine, session_factory, session_scope
from packages.storage.repositories.capture_items import CaptureItemRepository
from packages.storage.repositories.notes import NoteRepository
from packages.storage.repositories.reminders import ReminderRepository
from packages.storage.repositories.tasks import TaskRepository


def make_test_dir() -> Path:
    path = Path(__file__).resolve().parents[2] / "data" / "_test_tmp" / f"storage-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_repository_crud_with_tmp_sqlite() -> None:
    path = make_test_dir()
    try:
        engine = create_sqlite_engine(path / "notes.db")
        create_schema(engine)
        factory = session_factory(engine)

        with session_scope(factory) as session:
            capture = CaptureItemRepository(session).create(
                raw_text="Сегодня жим 70 на 8",
                user_id=10,
                chat_id=20,
                message_id=30,
            )
            note = NoteRepository(session).create(
                capture_item_id=capture.id,
                user_id=10,
                type="workout_log",
                category="workout",
                title="Жим лёжа",
                body="Сегодня жим 70 на 8",
                parsed_json={"type": "workout_log", "title": "Жим лёжа"},
            )
            task = TaskRepository(session).create(
                capture_item_id=capture.id,
                user_id=10,
                title="Купить магний",
            )
            reminder = ReminderRepository(session).create(
                user_id=10,
                task_id=task.id,
                remind_at_utc=datetime(2026, 7, 2, tzinfo=timezone.utc),
            )
            CaptureItemRepository(session).update_status(capture.id, status="parsed")

            assert capture.id > 0
            assert note.id > 0
            assert task.id > 0
            assert reminder.id > 0

        with session_scope(factory) as session:
            captures = CaptureItemRepository(session).recent_for_user(10)
            tasks = TaskRepository(session).active_for_user(10)

            assert captures[0].status == "parsed"
            assert tasks[0].title == "Купить магний"
    finally:
        shutil.rmtree(path, ignore_errors=True)
