FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY apps ./apps
COPY packages ./packages
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install --no-cache-dir .

RUN mkdir -p /app/data /app/logs /app/obsidian_vault

CMD ["python", "-m", "apps.telegram_bot.main"]
