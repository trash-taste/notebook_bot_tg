from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from packages.storage.db import create_sqlite_engine, session_factory, session_scope
from packages.storage.import_jsonl import import_jsonl_files
from packages.storage.repositories.capture_items import CaptureItemRepository
from packages.storage.repositories.tasks import TaskRepository


def make_test_dir() -> Path:
    path = Path(__file__).resolve().parents[2] / "data" / "_test_tmp" / f"import-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_import_jsonl_reports_counts_and_keeps_sources() -> None:
    path = make_test_dir()
    try:
        notes_jsonl = path / "notes.jsonl"
        tasks_jsonl = path / "tasks.jsonl"
        db_path = path / "notes.db"
        notes_jsonl.write_text(
            json.dumps(
                {
                    "chat_id": 20,
                    "user_id": 10,
                    "message_id": 30,
                    "received_at": "2026-07-02T10:00:00+00:00",
                    "raw_text": "Съел гречку",
                    "parser_result": {
                        "items": [
                            {
                                "type": "food_log",
                                "category": "food",
                                "title": "Гречка",
                                "raw_fragment": "Съел гречку",
                            }
                        ]
                    },
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        tasks_jsonl.write_text(
            json.dumps(
                {
                    "user_id": 10,
                    "title": "Купить магний",
                    "status": "active",
                    "created_at": "2026-07-02T10:00:00+00:00",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        counts = import_jsonl_files(
            db_path=db_path,
            notes_jsonl=notes_jsonl,
            tasks_jsonl=tasks_jsonl,
        )

        assert counts.captures == 1
        assert counts.notes == 1
        assert counts.tasks == 1
        assert counts.skipped_lines == 0
        assert notes_jsonl.exists()
        assert tasks_jsonl.exists()

        engine = create_sqlite_engine(db_path)
        factory = session_factory(engine)
        with session_scope(factory) as session:
            assert CaptureItemRepository(session).recent_for_user(10)[0].status == "imported"
            assert TaskRepository(session).active_for_user(10)[0].title == "Купить магний"
    finally:
        shutil.rmtree(path, ignore_errors=True)
