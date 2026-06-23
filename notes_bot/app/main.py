from __future__ import annotations

import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from pydantic import ValidationError

from app.config import Settings
from app.db import Database
from app.handlers import create_router
from app.llm_parser import OpenRouterParser


LOGGER = logging.getLogger(__name__)


async def main() -> int:
    try:
        settings = Settings()
    except ValidationError as exc:
        missing_fields = {
            str(error["loc"][0])
            for error in exc.errors()
            if error.get("loc")
        }
        env_names = {
            "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
            "openrouter_api_key": "OPENROUTER_API_KEY",
        }
        missing_env = [
            env_names[field]
            for field in sorted(missing_fields)
            if field in env_names
        ]
        suffix = ", ".join(missing_env) if missing_env else "обязательные значения"
        print(
            f"Ошибка конфигурации: заполни в .env: {suffix}.",
            file=sys.stderr,
        )
        return 1

    configure_logging(settings.log_level)

    database = Database(settings.db_path)
    database.initialize()
    parser = OpenRouterParser(settings)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(create_router(database, parser, settings))

    LOGGER.info("Starting notes bot with polling")
    await bot.delete_webhook(drop_pending_updates=False)
    await dispatcher.start_polling(
        bot,
        allowed_updates=dispatcher.resolve_used_update_types(),
    )
    return 0


def configure_logging(log_level: str) -> None:
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, log_level, logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    file_handler = RotatingFileHandler(
        logs_dir / "bot.log",
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.INFO)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
