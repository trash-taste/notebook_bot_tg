from __future__ import annotations

import os
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from src.voice_note_parser import cli
from src.voice_note_parser.config import ConfigError, load_settings
from tests.test_validate import valid_payload


class CliConfigTests(unittest.TestCase):
    def test_missing_api_key_is_clear_config_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigError):
                load_settings(env_path=Path("missing.env"), require_api_key=True)

    def test_missing_telegram_token_is_clear_config_error(self) -> None:
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            with self.assertRaises(ConfigError):
                load_settings(
                    env_path=Path("missing.env"),
                    require_api_key=True,
                    require_telegram_token=True,
                )

    def test_cli_rejects_empty_text_before_api_call(self) -> None:
        with patch("sys.stderr"):
            exit_code = cli.main(["   "])

        self.assertEqual(exit_code, 2)

    def test_cli_uses_parser_service_and_prints_json(self) -> None:
        with (
            patch("src.voice_note_parser.cli.parse_transcript", return_value=valid_payload()),
            patch("sys.stdout", new_callable=StringIO) as stdout,
        ):
            exit_code = cli.main(["завтра", "купить", "магний"])

        self.assertEqual(exit_code, 0)
        self.assertIn('"bot_reply": "Записал 1 задачу на завтра."', stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
