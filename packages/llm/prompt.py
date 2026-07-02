from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import DEFAULT_USER_TIMEZONE


PROMPT_PATH = Path(__file__).parent / "prompts" / "voice_note_parser_ru.md"
ALMATY_FALLBACK_TZ = timezone(timedelta(hours=5), DEFAULT_USER_TIMEZONE)


class PromptError(RuntimeError):
    """Raised when the prompt asset cannot be loaded or rendered."""


def load_prompt(prompt_path: Path = PROMPT_PATH) -> str:
    if not prompt_path.exists():
        raise PromptError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def render_prompt(
    *,
    user_timezone: str = DEFAULT_USER_TIMEZONE,
    now: datetime | None = None,
    prompt_path: Path = PROMPT_PATH,
) -> str:
    prompt = load_prompt(prompt_path)
    local_now = now or datetime.now(_timezone_for(user_timezone))

    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=_timezone_for(user_timezone))
    else:
        local_now = local_now.astimezone(_timezone_for(user_timezone))

    current_date = local_now.date()
    replacements = {
        "{{CURRENT_DATE}}": current_date.isoformat(),
        "{{CURRENT_DATETIME}}": local_now.isoformat(timespec="seconds"),
        "{{TOMORROW_DATE}}": (current_date + timedelta(days=1)).isoformat(),
        "{{USER_TIMEZONE}}": user_timezone,
    }

    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)

    missing = [placeholder for placeholder in replacements if placeholder in prompt]
    if missing:
        raise PromptError(
            "Не удалось заменить placeholders: " + ", ".join(sorted(missing))
        )

    return prompt


def _timezone_for(user_timezone: str):
    try:
        return ZoneInfo(user_timezone)
    except ZoneInfoNotFoundError:
        if user_timezone == DEFAULT_USER_TIMEZONE:
            return ALMATY_FALLBACK_TZ
        return timezone.utc

