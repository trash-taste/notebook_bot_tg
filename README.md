# Notebook Bot TG

Telegram-бот личных заметок: задачи, питание, тренировки, обычные заметки, OpenRouter-парсинг и Obsidian Daily Notes.

## Структура

```text
apps/telegram_bot/      # aiogram bot для VPS
packages/llm/           # CLI/OpenRouter parser и prompt
packages/llm/prompts/   # voice_note_parser_ru.md
data/                   # локальные данные, в Git не добавлять без явного решения
scripts/                # ручные scripts
tests/                  # тесты
```

## Настройка

Создай `.env` из `.env.example` и заполни секреты:

```env
TELEGRAM_BOT_TOKEN=
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openai/gpt-4o-mini
DB_PATH=/app/data/notes.db
USER_TIMEZONE=Asia/Almaty
LOG_LEVEL=INFO
OBSIDIAN_VAULT_PATH=/app/obsidian_vault
ENABLE_OBSIDIAN_EXPORT=true
HOST_OBSIDIAN_VAULT_PATH=./obsidian_vault
```

Секреты не коммитить.

## Локальный запуск

```bash
python -m pip install -e ".[dev]"
python -m apps.telegram_bot.main
```

CLI parser:

```bash
parse-note "Сегодня сделал жим 70 на 8, ел гречку, завтра купить магний"
```

или:

```bash
python -m packages.llm.cli "Сегодня сделал жим 70 на 8"
```

## Docker / VPS

На VPS папка остаётся простой:

```bash
cd /opt/notebook_bot_tg
git pull
docker compose up -d --build
docker compose logs --tail=80 notes-bot
```

Docker service:

```text
notes-bot
```

Команда контейнера:

```bash
python -m apps.telegram_bot.main
```

## Команды бота

- `/start`
- `/today`
- `/tasks`
- `/food`
- `/workout`
- `/last`
- `/undo`
- `/context`
- `/export_today`
- `/rebuild_today`
- `/health`

## Obsidian

SQLite остаётся основной базой, Obsidian — Markdown-отображение.

Daily notes:

```text
obsidian_vault/Daily/YYYY-MM-DD.md
```

Бот обновляет только блок:

```text
<!-- BOT-GENERATED:START -->
<!-- BOT-GENERATED:END -->
```

Ручной текст вне блока не трогается.

## Backup

`scripts/backup.sh` намеренно защищён от случайного коммита личных данных:

```bash
ALLOW_DATA_GIT_BACKUP=1 scripts/backup.sh
```

Используй только если remote приватный и ты понимаешь, что `data/` может содержать личные заметки.

## Проверки

```bash
pytest
python -m compileall -q apps packages tests
```
