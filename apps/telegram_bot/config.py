from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    telegram_bot_token: str
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"
    db_path: Path = Path("/app/data/notes.db")
    obsidian_vault_path: Path | None = Path("/app/obsidian_vault")
    enable_obsidian_export: bool = True
    user_timezone: str = Field(
        default="Asia/Almaty",
        validation_alias=AliasChoices("USER_TIMEZONE", "TIMEZONE"),
    )
    log_level: str = "INFO"

    @field_validator("telegram_bot_token", "openrouter_api_key")
    @classmethod
    def validate_secret(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Required secret is empty")
        return value

    @field_validator("openrouter_base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @field_validator("obsidian_vault_path", mode="before")
    @classmethod
    def normalize_optional_path(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("user_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        value = value.strip()
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc
        return value
