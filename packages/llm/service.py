from __future__ import annotations

from typing import Any

from .config import Settings, load_settings
from .openrouter import request_completion
from .prompt import render_prompt
from .validate import parse_model_json, validate_parser_response


class ParserInputError(ValueError):
    """Raised when the user transcript cannot be sent to the parser."""


def parse_transcript(
    transcript: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cleaned_transcript = transcript.strip()
    if not cleaned_transcript:
        raise ParserInputError("Текст заметки пустой.")

    runtime_settings = settings or load_settings(require_api_key=True)
    system_prompt = render_prompt(user_timezone=runtime_settings.user_timezone)
    model_content = request_completion(
        settings=runtime_settings,
        system_prompt=system_prompt,
        transcript=cleaned_transcript,
    )
    parsed = parse_model_json(model_content)
    return validate_parser_response(parsed)
