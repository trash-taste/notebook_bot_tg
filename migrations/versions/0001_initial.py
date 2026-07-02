"""initial storage schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capture_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("chat_id", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("parser_error", sa.Text(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_capture_items_user_id", "capture_items", ["user_id"])
    op.create_index("ix_capture_items_chat_id", "capture_items", ["chat_id"])
    op.create_index("ix_capture_items_status", "capture_items", ["status"])
    op.create_index("ix_capture_items_created_at_utc", "capture_items", ["created_at_utc"])
    op.create_index("ix_capture_items_updated_at_utc", "capture_items", ["updated_at_utc"])

    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("capture_item_id", sa.Integer(), sa.ForeignKey("capture_items.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("parsed_json", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notes_user_id", "notes", ["user_id"])
    op.create_index("ix_notes_type", "notes", ["type"])
    op.create_index("ix_notes_category", "notes", ["category"])
    op.create_index("ix_notes_created_at_utc", "notes", ["created_at_utc"])
    op.create_index("ix_notes_updated_at_utc", "notes", ["updated_at_utc"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("capture_item_id", sa.Integer(), sa.ForeignKey("capture_items.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("due_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_type", sa.Text(), nullable=True),
        sa.Column("priority", sa.Text(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_due_at_utc", "tasks", ["due_at_utc"])
    op.create_index("ix_tasks_created_at_utc", "tasks", ["created_at_utc"])
    op.create_index("ix_tasks_updated_at_utc", "tasks", ["updated_at_utc"])

    op.create_table(
        "reminders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("remind_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reminders_user_id", "reminders", ["user_id"])
    op.create_index("ix_reminders_remind_at_utc", "reminders", ["remind_at_utc"])
    op.create_index("ix_reminders_status", "reminders", ["status"])


def downgrade() -> None:
    op.drop_table("reminders")
    op.drop_table("tasks")
    op.drop_table("notes")
    op.drop_table("capture_items")
