from __future__ import annotations

import argparse
import json
import sys

from .config import ConfigError
from .openrouter import OpenRouterError
from .prompt import PromptError
from .service import ParserInputError, parse_transcript
from .validate import ValidationError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Parse a Telegram voice-note transcript through OpenRouter.",
    )
    parser.add_argument(
        "text",
        nargs="*",
        help="Recognized voice-note text. Wrap it in quotes for best results.",
    )

    args = parser.parse_args(argv)
    transcript = " ".join(args.text).strip()
    if not transcript:
        print("Ошибка: передай текст заметки первым аргументом.", file=sys.stderr)
        return 2

    try:
        validated = parse_transcript(transcript)
    except (
        ConfigError,
        ParserInputError,
        PromptError,
        OpenRouterError,
        ValidationError,
    ) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    json.dump(validated, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
