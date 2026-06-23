# Notes Bot: запуск и деплой

## Что нужно

- Python 3.12 для локального запуска.
- Docker Engine и Docker Compose plugin для запуска в контейнере.
- Telegram bot token от BotFather.
- OpenRouter API key.

Секреты хранятся только в `.env`. Не добавляй `.env` в Git.

## 1. Локальный запуск

Перейди в каталог проекта:

```bash
cd notes_bot
```

Создай виртуальное окружение:

Linux/macOS:

```bash
python3.12 -m venv .venv
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
```

Активируй его.

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Установи зависимости:

```bash
python -m pip install -r requirements.txt
```

Для локального запуска укажи относительный путь к SQLite:

```env
DB_PATH=./data/notes.db
```

Запусти бота:

```bash
python -m app.main
```

## 2. Создание `.env`

Создай `.env` на основе `.env.example`:

```bash
cp .env.example .env
```

Заполни секреты:

```env
TELEGRAM_BOT_TOKEN=telegram-token
OPENROUTER_API_KEY=openrouter-key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openai/gpt-4o-mini
DB_PATH=/app/data/notes.db
USER_TIMEZONE=Asia/Almaty
LOG_LEVEL=INFO
```

Значения `TELEGRAM_BOT_TOKEN` и `OPENROUTER_API_KEY` не должны оставаться пустыми.
Не отправляй реальные ключи в чат и не добавляй `.env` в Git.

Для локального запуска без Docker замени `DB_PATH` на `./data/notes.db`.

## 3. Запуск через Docker Compose

Собери и запусти контейнер:

```bash
docker compose up -d --build
```

Проверь состояние:

```bash
docker compose ps
```

Бот работает через polling. Webhook, домен и открытые HTTP-порты не нужны.

## 4. Просмотр логов

Логи Docker:

```bash
docker compose logs -f notes-bot
```

Файловый лог:

```bash
tail -f logs/bot.log
```

## 5. Остановка бота

Остановить и удалить контейнер:

```bash
docker compose down
```

Остановить без удаления контейнера:

```bash
docker compose stop notes-bot
```

## 6. Backup SQLite

Создай каталог для backup:

```bash
mkdir -p backups
```

Для согласованной копии сначала останови контейнер:

```bash
docker compose stop notes-bot
cp data/notes.db "backups/notes-$(date +%F-%H%M%S).db"
docker compose start notes-bot
```

Проверь, что backup появился:

```bash
ls -lh backups/
```

## 7. Обновление на VPS Ubuntu 24.04

Перейди в каталог проекта и получи новую версию:

```bash
cd /opt/notes_bot
git pull
```

Сделай backup базы перед обновлением:

```bash
mkdir -p backups
docker compose stop notes-bot
cp data/notes.db "backups/notes-$(date +%F-%H%M%S).db"
```

Пересобери и запусти:

```bash
docker compose up -d --build
```

Проверь логи:

```bash
docker compose logs --tail=100 notes-bot
```

Данные SQLite и логи сохраняются в host-каталогах `data/` и `logs/`, поэтому пересборка контейнера их не удаляет.
