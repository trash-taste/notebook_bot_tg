from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from packages.storage.db import session_scope
from packages.storage.repositories.capture_items import CaptureItemRepository
from apps.telegram_bot.db import Database


def make_test_dir() -> Path:
    path = Path(__file__).resolve().parents[2] / "data" / "_test_tmp" / f"capture-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_capture_can_be_saved_before_parser_failure() -> None:
    path = make_test_dir()
    try:
        database = Database(path / "notes.db")
        database.initialize()

        capture_id = database.create_capture(
            user_id=10,
            chat_id=20,
            message_id=30,
            raw_text="сырой текст до LLM",
        )
        database.mark_capture_status(
            capture_id,
            "parse_failed",
            parser_error="LLM timeout",
        )

        with session_scope(database.session_factory) as session:
            capture = CaptureItemRepository(session).get(capture_id)
            assert capture is not None
            assert capture.raw_text == "сырой текст до LLM"
            assert capture.status == "parse_failed"
            assert capture.parser_error == "LLM timeout"
    finally:
        shutil.rmtree(path, ignore_errors=True)
