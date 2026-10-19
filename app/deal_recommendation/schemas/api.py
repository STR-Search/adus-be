from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CreateConversationPayload(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ConversationSummary(BaseModel):
    id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationListResult(BaseModel):
    items: list[ConversationSummary]


class PostMessagePayload(BaseModel):
    text: str = Field(min_length=1, max_length=50000)


class TurnRun(BaseModel):
    id: UUID
    status: str
    cost_usd: Decimal | None
    error: str | None = None


class ToolStep(BaseModel):
    tool: str
    is_error: bool
    duration_ms: int


class DealCard(BaseModel):
    rank: int
    underwriting_id: int
    match_score: Decimal | None
    why: str
    matched: list[str]
    missed: list[str]
    snapshot: dict[str, Any]


class Turn(BaseModel):
    user_text: str
    run: TurnRun | None
    assistant_text: str
    tool_steps: list[ToolStep]
    profile: dict[str, Any] | None
    cards: list[DealCard]
    summary: str | None = None


class ConversationDetail(BaseModel):
    id: UUID
    title: str | None
    turns: list[Turn]


class TraceToolCall(BaseModel):
    seq: int
    tool_name: str
    input: dict[str, Any]
    output: dict[str, Any]
    is_error: bool
    duration_ms: int


class RunTrace(BaseModel):
    run: dict[str, Any]
    tool_calls: list[TraceToolCall]
