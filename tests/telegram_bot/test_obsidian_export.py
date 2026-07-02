from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from apps.telegram_bot.obsidian import BOT_BLOCK_END, BOT_BLOCK_START, ObsidianExporter


def temporary_directory() -> Path:
    root = Path(__file__).resolve().parents[2] / "data" / "_test_tmp"
    path = root / f"obsidian-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class ObsidianExportTests(unittest.TestCase):
    def test_rebuild_daily_note_preserves_manual_text_and_updates_bot_block(self) -> None:
        temp_dir = temporary_directory()
        try:
            exporter = ObsidianExporter(temp_dir)
            daily_path = temp_dir / "Daily" / "2026-06-25.md"
            daily_path.parent.mkdir(parents=True)
            daily_path.write_text(
                "\n".join(
                    [
                        "# 2026-06-25",
                        "",
                        "## 📝 Ручные мысли",
                        "",
                        "Моя ручная мысль, которую бот не должен трогать.",
                        "",
                        BOT_BLOCK_START,
                        "старый бот-блок",
                        BOT_BLOCK_END,
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            path = exporter.rebuild_daily_note(
                user_id=10,
                date="2026-06-25",
                items=[
                    {
                        "id": 45,
                        "type": "workout_log",
                        "title": "Жим лёжа",
                        "status": "active",
                        "data_json": (
                            '{"exercises":[{"exercise":"Жим лёжа",'
                            '"weight_kg":70,"reps":8}]}'
                        ),
                        "obsidian_block_id": "workout-45",
                    }
                ],
            )

            self.assertEqual(path, daily_path)
            content = daily_path.read_text(encoding="utf-8")
            self.assertIn("Моя ручная мысль", content)
            self.assertNotIn("старый бот-блок", content)
            self.assertIn("<!-- item:workout-45 -->", content)
            self.assertIn("Жим лёжа: 70 кг, 8 повт.", content)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_disabled_exporter_does_nothing(self) -> None:
        temp_dir = temporary_directory()
        try:
            exporter = ObsidianExporter(temp_dir, enabled=False)

            path = exporter.rebuild_daily_note(
                user_id=10,
                date="2026-06-25",
                items=[],
            )

            self.assertIsNone(path)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
