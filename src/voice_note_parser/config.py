from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"
DEFAULT_USER_TIMEZONE = "Asia/Almaty"


class ConfigError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str
    openrouter_model: str
    user_timezone: str
    openrouter_api_url: str
    http_referer: str | None
    app_title: str | None
    telegram_bot_token: str


def load_settings(
    *,
    env_path: Path | None = None,
    require_api_key: bool = True,
    require_telegram_token: bool = False,
) -> Settings:
    """Load settings from .env and process environment variables."""

    load_env_file(env_path or DEFAULT_ENV_PATH)

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if require_api_key and not api_key:
        raise ConfigError(
            "OPENROUTER_API_KEY не найден. Создай .env на основе .env.example "
            "и добавь туда ключ OpenRouter."
        )

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if require_telegram_token and not telegram_bot_token:
        raise ConfigError(
            "TELEGRAM_BOT_TOKEN не найден. Добавь токен Telegram-бота в .env."
        )

    return Settings(
        openrouter_api_key=api_key,
        openrouter_model=os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL).strip()
        or DEFAULT_MODEL,
        user_timezone=os.getenv("USER_TIMEZONE", DEFAULT_USER_TIMEZONE).strip()
        or DEFAULT_USER_TIMEZONE,
        openrouter_api_url=os.getenv(
            "OPENROUTER_API_URL",
            DEFAULT_OPENROUTER_API_URL,
        ).strip()
        or DEFAULT_OPENROUTER_API_URL,
        http_referer=_optional_env("OPENROUTER_HTTP_REFERER"),
        app_title=_optional_env("OPENROUTER_APP_TITLE"),
        telegram_bot_token=telegram_bot_token,
    )


def load_env_file(env_path: Path) -> None:
    """Load .env with python-dotenv when available, with a small fallback."""

    if not env_path.exists():
        return

    try:
        from dotenv import load_dotenv
    except ImportError:
        _load_env_file_fallback(env_path)
        return

    load_dotenv(env_path)


def _load_env_file_fallback(env_path: Path) -> None:
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue

        os.environ[key] = _strip_quotes(value.strip())


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _optional_env(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None
