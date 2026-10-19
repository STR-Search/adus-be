from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

Emit = Callable[[str, dict], Awaitable[None]]


async def _noop(event: str, data: dict) -> None:
    return None


@dataclass
class PoolOverride:
    """Eval-only candidate pool. Set by the harness; the model never sees it."""

    statuses: list[str]
    approved_from: date
    approved_to: date
    property_pending: bool | None = None


@dataclass
class RunContext:
    """Per-run state shared by the tools and the agent loop."""

    conversation_id: UUID
    run_id: UUID
    down_payment_pct: Decimal | None = None
    interest_rate: Decimal | None = None
    already_shown_ids: set[int] = field(default_factory=set)
    seen_ids: set[int] = field(default_factory=set)
    last_scores: dict[int, float] = field(default_factory=dict)
    max_candidates_seen: int = 0
    shortlist_presented: bool = False
    tool_calls: int = 0
    budget_exhausted: bool = False
    pool_override: PoolOverride | None = None
    emit: Emit = _noop
