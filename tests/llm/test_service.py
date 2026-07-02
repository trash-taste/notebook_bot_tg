from __future__ import annotations

import unittest
from unittest.mock import patch

from packages.llm.config import Settings
from packages.llm.service import ParserInputError, parse_transcript
from tests.llm.test_validate import valid_payload


def make_settings() -> Settings:
    return Settings(
        openrouter_api_key="test-openrouter-key",
        openrouter_model="openai/gpt-4o-mini",
        user_timezone="Asia/Almaty",
        openrouter_api_url="https://openrouter.ai/api/v1/chat/completions",
        http_referer=None,
        app_title="T Bot Notes",
        telegram_bot_token="test-telegram-token",
    )


class ServiceTests(unittest.TestCase):
    def test_parse_transcript_calls_prompt_openrouter_and_validation(self) -> None:
        payload = valid_payload()

        with (
            patch("packages.llm.service.render_prompt", return_value="prompt") as render,
            patch(
                "packages.llm.service.request_completion",
                return_value='{"raw_text":"ok"}',
            ) as request,
            patch(
                "packages.llm.service.parse_model_json",
                return_value={"raw_text": "ok"},
            ) as parse_json,
            patch(
                "packages.llm.service.validate_parser_response",
                return_value=payload,
            ) as validate,
        ):
            result = parse_transcript("  завтра купить магний  ", settings=make_settings())

        self.assertEqual(result, payload)
        render.assert_called_once_with(user_timezone="Asia/Almaty")
        request.assert_called_once()
        self.assertEqual(request.call_args.kwargs["transcript"], "завтра купить магний")
        parse_json.assert_called_once_with('{"raw_text":"ok"}')
        validate.assert_called_once_with({"raw_text": "ok"})

    def test_parse_transcript_rejects_empty_text(self) -> None:
        with self.assertRaises(ParserInputError):
            parse_transcript("  ", settings=make_settings())


if __name__ == "__main__":
    unittest.main()
