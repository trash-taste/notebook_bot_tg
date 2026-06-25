from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.context import BotContext
from app.llm_parser import LLMParserError, _strip_code_fence
from app.models import IntentResult
from app.prompts import build_intent_prompt


class IntentParser:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def detect(self, raw_text: str, context: BotContext) -> IntentResult:
        prompt = build_intent_prompt(
            user_text=raw_text,
            current_date=context.current_date,
            timezone_name=context.timezone_name,
            context=context.to_prompt_dict(),
        )
        payload = {
            "model": self.settings.openrouter_model,
            "messages": [
                {
                    "role": "system",
                    "content": prompt,
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
            "max_tokens": 1200,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(
                    f"{self.settings.openrouter_base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            details = exc.response.text[:500]
            raise LLMParserError(
                f"OpenRouter intent HTTP {exc.response.status_code}: {details}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMParserError(f"OpenRouter intent request failed: {exc}") from exc

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMParserError("OpenRouter returned unexpected intent shape") from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMParserError("OpenRouter returned empty intent JSON")

        try:
            parsed_json = json.loads(_strip_code_fence(content))
            return IntentResult.model_validate(parsed_json)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LLMParserError(f"Intent JSON validation failed: {exc}") from exc
