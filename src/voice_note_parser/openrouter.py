from __future__ import annotations

from typing import Any

from .config import Settings


class OpenRouterError(RuntimeError):
    """Raised when the OpenRouter request fails or returns an unexpected shape."""


def request_completion(
    *,
    settings: Settings,
    system_prompt: str,
    transcript: str,
    timeout_seconds: int = 60,
) -> str:
    try:
        import requests
    except ImportError as exc:
        raise OpenRouterError(
            "Пакет requests не установлен. Выполни: "
            "python -m pip install -r requirements.txt"
        ) from exc

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    if settings.http_referer:
        headers["HTTP-Referer"] = settings.http_referer
    if settings.app_title:
        headers["X-OpenRouter-Title"] = settings.app_title

    payload: dict[str, Any] = {
        "model": settings.openrouter_model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcript},
        ],
    }

    try:
        response = requests.post(
            settings.openrouter_api_url,
            headers=headers,
            json=payload,
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        raise OpenRouterError(f"Ошибка запроса к OpenRouter: {exc}") from exc

    if response.status_code >= 400:
        raise OpenRouterError(
            f"OpenRouter вернул HTTP {response.status_code}: {response.text[:500]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise OpenRouterError("OpenRouter вернул не JSON-ответ.") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenRouterError("В ответе OpenRouter нет choices[0].message.content.") from exc

    if not isinstance(content, str) or not content.strip():
        raise OpenRouterError("OpenRouter вернул пустой content.")

    return content.strip()

