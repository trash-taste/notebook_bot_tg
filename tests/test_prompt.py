from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.voice_note_parser.prompt import render_prompt


class PromptTests(unittest.TestCase):
    def test_render_prompt_replaces_runtime_placeholders(self) -> None:
        rendered = render_prompt(
            user_timezone="Asia/Almaty",
            now=datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc),
        )

        self.assertNotIn("{{CURRENT_DATE}}", rendered)
        self.assertNotIn("{{CURRENT_DATETIME}}", rendered)
        self.assertNotIn("{{TOMORROW_DATE}}", rendered)
        self.assertNotIn("{{USER_TIMEZONE}}", rendered)
        self.assertIn("2026-01-15", rendered)
        self.assertIn("2026-01-16", rendered)
        self.assertIn("Asia/Almaty", rendered)


if __name__ == "__main__":
    unittest.main()

