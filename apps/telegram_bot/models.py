from __future__ import annotations

from datetime import date as Date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ItemType = Literal["task", "workout_log", "food_log", "general_note"]
Category = Literal["task", "workout", "food", "general"]
DueType = Literal[
    "today",
    "tomorrow",
    "this_week",
    "specific_date",
    "no_deadline",
    "unknown",
]
Priority = Literal["low", "normal", "high"]
Status = Literal["active", "done"]
Intent = Literal[
    "create_new_item",
    "append_to_existing_item",
    "update_existing_item",
    "archive_item",
    "query_items",
    "clarification_needed",
]
IntentTargetType = Literal["task", "workout_log", "food_log", "general_note"]


class ParsedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ItemType
    category: Category
    title: str = Field(min_length=1, max_length=300)
    date: Date | None = None
    due_type: DueType | None = None
    due_date: Date | None = None
    priority: Priority | None = None
    status: Status | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    raw_fragment: str
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    needs_clarification: bool = False

    @model_validator(mode="after")
    def validate_category(self) -> "ParsedItem":
        expected = {
            "task": "task",
            "workout_log": "workout",
            "food_log": "food",
            "general_note": "general",
        }[self.type]
        if self.category != expected:
            raise ValueError(f"category must be {expected!r} for type {self.type!r}")
        return self


class ParsedSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tasks_count: int = Field(ge=0)
    workout_count: int = Field(ge=0)
    food_count: int = Field(ge=0)
    general_notes_count: int = Field(ge=0)


class ParsedNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str
    detected_language: str = Field(min_length=2, max_length=20)
    items: list[ParsedItem] = Field(default_factory=list)
    summary: ParsedSummary
    bot_reply: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_summary_counts(self) -> "ParsedNote":
        expected = {
            "tasks_count": sum(item.type == "task" for item in self.items),
            "workout_count": sum(item.type == "workout_log" for item in self.items),
            "food_count": sum(item.type == "food_log" for item in self.items),
            "general_notes_count": sum(item.type == "general_note" for item in self.items),
        }
        actual = self.summary.model_dump()
        if actual != expected:
            raise ValueError(f"summary counts do not match items: expected {expected}")
        return self


class IntentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent
    target_type: IntentTargetType | None = None
    target_item_id: int | None = None
    target_date: str | None = None
    action: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    needs_clarification: bool = False
    clarification_question: str | None = None
    candidate_item_ids: list[int] = Field(default_factory=list)
