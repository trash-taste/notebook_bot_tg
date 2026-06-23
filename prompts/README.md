# Voice Note Parser Prompt

This directory contains prompt assets for parsing Telegram voice-note transcripts into strict JSON.

## Files

- `voice_note_parser_ru.md` - Russian system prompt for extracting tasks, workouts, food logs, and general notes.

## Runtime Placeholders

Before sending the prompt to the model, replace these placeholders:

| Placeholder | Example | Notes |
| --- | --- | --- |
| `{{CURRENT_DATE}}` | `2026-01-15` | User-local current date in `YYYY-MM-DD`. |
| `{{CURRENT_DATETIME}}` | `2026-01-15T14:30:00+05:00` | User-local current datetime. |
| `{{TOMORROW_DATE}}` | `2026-01-16` | Next calendar date in the user's timezone. |
| `{{USER_TIMEZONE}}` | `Asia/Almaty` | Default to `Asia/Almaty`, but keep injectable per user. |

Do not hardcode dates into the prompt asset. Compute them at request time from the user's timezone.

## Expected Usage

Use `voice_note_parser_ru.md` as the system or developer prompt. Send the recognized voice transcript as the user message.

The model response must be valid JSON only:

- No Markdown.
- No code fences.
- No explanatory text outside JSON.
- Missing scalar values must be `null`.
- If nothing useful is detected, return `"items": []` and zero summary counts.

## Validation Checklist

After receiving the model response, bot code should validate:

- Top-level keys are exactly the expected contract: `raw_text`, `detected_language`, `items`, `summary`, `bot_reply`.
- Every item has `type`, `category`, `title`, `date`, `due_type`, `due_date`, `priority`, `status`, `data`, `raw_fragment`, `missing_fields`, `confidence`, and `needs_clarification`.
- `type` is only one of `task`, `workout_log`, `food_log`, `general_note`.
- `category` matches the item type: `task`, `workout`, `food`, or `general`.
- `due_type` is a task deadline classifier, not an item type.
- `summary` counts match the actual items array.
- `bot_reply` is short enough for Telegram and mentions what was recorded.

## Smoke-Test Transcripts

Use these examples to test prompt behavior after integration:

1. Mixed note:
   `Сегодня сделал жим 70 на 8, ел гречку с курицей, завтра купить магний, идея сделать недельный отчет.`

2. Task deadlines:
   `Сегодня оплатить интернет, завтра позвонить врачу, на этой неделе разобрать документы, пятого июля купить билеты, потом как-нибудь посмотреть курс.`

3. Workout extraction:
   `Присед 100 на 5, потом 3 подхода по 10 подтягивания, спина немного устала, но прогресс нормальный.`

4. Food extraction:
   `На завтрак два яйца и кофе, днем 300 грамм курицы, вечером кефир без точного количества.`

5. General note:
   `Мысль: бот должен показывать недельную динамику привычек, но пока это просто идея.`

6. Empty or unusable transcript:
   `Эээ, ну, короче, потом скажу.`

## Scope

This prompt asset does not include Telegram bot code, database models, Google Sheets export, LLM API calls, or JSON schema code. Those can be added later around this stable prompt contract.
