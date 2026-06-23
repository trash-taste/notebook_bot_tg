from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.telegram_bot.storage import append_note_record


class StorageTests(unittest.TestCase):
    def test_append_note_record_writes_one_jsonl_line(self) -> None:
        path = Path("tests") / "_notes_test.jsonl"
        try:
            path.unlink(missing_ok=True)
            append_note_record(
                {
                    "chat_id": 1,
                    "user_id": 2,
                    "message_id": 3,
                    "received_at": "2026-01-15T10:00:00+00:00",
                    "raw_text": "завтра купить магний",
                    "parser_result": {"bot_reply": "Записал задачу."},
                },
                path=path,
            )

            lines = path.read_text(encoding="utf-8").splitlines()
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(len(lines), 1)
        parsed = json.loads(lines[0])
        self.assertEqual(parsed["raw_text"], "завтра купить магний")
        self.assertEqual(parsed["parser_result"]["bot_reply"], "Записал задачу.")


if __name__ == "__main__":
    unittest.main()
