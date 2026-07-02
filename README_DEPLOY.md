# Deploy

Основная инструкция теперь в [README.md](README.md).

Короткий VPS flow:

```bash
cd /opt/notebook_bot_tg
git pull
docker compose up -d --build
docker compose logs --tail=80 notes-bot
```

Папка Obsidian на VPS:

```text
/opt/notebook_bot_tg/obsidian_vault
```

SQLite внутри контейнера:

```text
/app/data/notes.db
```
