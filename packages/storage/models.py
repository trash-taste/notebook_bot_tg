from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CaptureItem(Base):
    __tablename__ = "capture_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    chat_id: Mapped[int | None] = mapped_column(Integer, index=True)
    message_id: Mapped[int | None] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, default="text")
    status: Mapped[str] = mapped_column(Text, default="received", index=True)
    parser_error: Mapped[str | None] = mapped_column(Text)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    notes: Mapped[list[Note]] = relationship(back_populates="capture_item")
    tasks: Mapped[list[Task]] = relationship(back_populates="capture_item")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    capture_item_id: Mapped[int | None] = mapped_column(ForeignKey("capture_items.id"))
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    type: Mapped[str] = mapped_column(Text, index=True)
    category: Mapped[str] = mapped_column(Text, index=True)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    parsed_json: Mapped[str] = mapped_column(Text)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    archived_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    capture_item: Mapped[CaptureItem | None] = relationship(back_populates="notes")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    capture_item_id: Mapped[int | None] = mapped_column(ForeignKey("capture_items.id"))
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="active", index=True)
    due_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    due_type: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str | None] = mapped_column(Text)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    archived_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    capture_item: Mapped[CaptureItem | None] = relationship(back_populates="tasks")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))
    remind_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(Text, default="active", index=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
