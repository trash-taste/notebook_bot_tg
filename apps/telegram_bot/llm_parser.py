from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from pydantic import ValidationError

from apps.telegram_bot.config import Settings
from apps.telegram_bot.models import ParsedNote
from apps.telegram_bot.prompts import build_system_prompt


class LLMParserError(RuntimeError):
    """Raised when the LLM request or structured parsing fails."""


class OpenRouterParser:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def parse(self, raw_text: str) -> ParsedNote:
        raw_text = raw_text.strip()
        if not raw_text:
            raise LLMParserError("Note text is empty")

        now = datetime.now(self._timezone())
        payload = {
            "model": self.settings.openrouter_model,
            "messages": [
                {
                    "role": "system",
                    "content": build_system_prompt(now, self.settings.user_timezone),
                },
                {"role": "user", "content": raw_text},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 2500,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.settings.openrouter_base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            details = exc.response.text[:500]
            raise LLMParserError(
                f"OpenRouter returned HTTP {exc.response.status_code}: {details}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMParserError(f"OpenRouter request failed: {exc}") from exc

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMParserError("OpenRouter returned an unexpected response shape") from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMParserError("OpenRouter returned empty JSON content")

        try:
            parsed_json = json.loads(_strip_code_fence(content))
            parsed_note = ParsedNote.model_validate(parsed_json)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LLMParserError(f"OpenRouter JSON validation failed: {exc}") from exc

        if parsed_note.raw_text != raw_text:
            parsed_note = parsed_note.model_copy(update={"raw_text": raw_text})
        return parsed_note

    def _timezone(self):
        try:
            return ZoneInfo(self.settings.user_timezone)
        except ZoneInfoNotFoundError as exc:
            raise LLMParserError(
                f"Unknown timezone: {self.settings.user_timezone}"
            ) from exc


def _strip_code_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        return "\n".join(lines[1:-1]).strip()
    return stripped
