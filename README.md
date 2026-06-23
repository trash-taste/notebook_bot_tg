# T Bot Notes

Минимальная интеграция для проверки prompt asset парсера голосовых заметок через OpenRouter.

## Настройка

1. Создай локальный `.env` на основе `.env.example`.
2. Добавь ключи:

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openai/gpt-4o-mini
USER_TIMEZONE=Asia/Almaty
TELEGRAM_BOT_TOKEN=123456:telegram-token
```

3. Установи зависимости:

```powershell
python -m pip install -r requirements.txt
```

## Запуск CLI

```powershell
python -m src.voice_note_parser.cli "Сегодня сделал жим 70 на 8, ел гречку, завтра купить магний"
```

CLI загружает `prompts/voice_note_parser_ru.md`, подставляет текущие даты и часовой пояс, отправляет текст в OpenRouter и печатает валидированный JSON.

## Запуск Telegram-бота

```powershell
python -m src.telegram_bot.bot
```

Бот принимает текстовые сообщения, отправляет их в parser, отвечает коротким `bot_reply` и сохраняет полный результат в `data/notes.jsonl`.

Голосовые сообщения бот не распознает отдельным API, чтобы снизить стоимость. Для диктовки используй голосовой ввод клавиатуры телефона и отправляй уже готовый текст.

## Главное меню

Команда `/start` или `/menu` показывает меню:

```text
Что показать?

[📅 Сегодня] [✅ Задачи]
[🏋️ Тренировки] [🍽 Питание]
[📈 Прогресс] [📝 Все заметки]
```

Меню не вызывает дополнительные дорогие STT-запросы: оно работает по уже сохраненным `notes.jsonl` и `tasks.jsonl`.

## Активные задачи

После парсинга заметок бот сохраняет найденные задачи в `data/tasks.jsonl`.

Команда:

```text
/tasks
```

показывает активные задачи с inline-кнопками:

- `✅ Выполнено` - закрыть задачу.
- `📆 Перенести` - выбрать быстрый срок: сегодня, завтра, эта неделя, без срока.
- `✏️ Изменить` - отправить новое название задачи следующим сообщением.

## Конфигурация

- `OPENROUTER_API_KEY` - обязательный ключ OpenRouter.
- `OPENROUTER_MODEL` - модель OpenRouter, по умолчанию `openai/gpt-4o-mini`.
- `USER_TIMEZONE` - часовой пояс пользователя, по умолчанию `Asia/Almaty`.
- `TELEGRAM_BOT_TOKEN` - обязательный токен Telegram-бота для запуска `src.telegram_bot.bot`.
- `OPENROUTER_HTTP_REFERER` - необязательный URL для OpenRouter rankings.
- `OPENROUTER_APP_TITLE` - необязательное название приложения для OpenRouter rankings.

Реальный `.env` игнорируется Git и не должен попадать в репозиторий.

## Локальные проверки

```powershell
python -m unittest discover -s tests
```
