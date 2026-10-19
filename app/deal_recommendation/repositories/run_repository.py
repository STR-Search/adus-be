from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.deal_recommendation.models import AgentRun, ToolCall

# claude-sonnet-5-5, USD per 1M tokens.
_PRICE_PER_MTOK = {
    "input": Decimal("2.00"),
    "output": Decimal("10.00"),
    "cache_read": Decimal("0.20"),
    "cache_write": Decimal("2.50"),
}


@dataclass
class RunUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def add(self, usage) -> None:
        """Accumulate an Anthropic ``usage`` object (missing fields count as 0)."""
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0

    def cost_usd(self) -> Decimal:
        total = (
            self.input_tokens * _PRICE_PER_MTOK["input"]
            + self.output_tokens * _PRICE_PER_MTOK["output"]
            + self.cache_read_tokens * _PRICE_PER_MTOK["cache_read"]
            + self.cache_write_tokens * _PRICE_PER_MTOK["cache_write"]
        ) / Decimal(1_000_000)
        return total.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def as_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
        }


class RunRepository:
    """Agent runs and their tool-call trace. Callers own commits."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_run(
        self, *, conversation_id: UUID, user_message_id: int, model: str, effort: str
    ) -> AgentRun:
        run = AgentRun(
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            model=model,
            effort=effort,
            status="running",
        )
        self.db.add(run)
        await self.db.flush()
        await self.db.refresh(run)
        return run

    async def finish_run(
        self,
        run_id: UUID,
        *,
        status: str,
        stop_reason: str | None,
        iterations: int,
        usage: RunUsage,
        error: str | None,
    ) -> None:
        await self.db.execute(
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(
                status=status,
                stop_reason=stop_reason,
                iterations=iterations,
                cost_usd=usage.cost_usd(),
                error=error,
                finished_at=func.now(),
                **usage.as_dict(),
            )
        )

    async def add_tool_call(
        self,
        *,
        run_id: UUID,
        seq: int,
        tool_use_id: str | None,
        tool_name: str,
        input: dict,
        output: dict,
        is_error: bool,
        duration_ms: int,
    ) -> None:
        self.db.add(
            ToolCall(
                run_id=run_id,
                seq=seq,
                tool_use_id=tool_use_id,
                tool_name=tool_name,
                input=input,
                output=output,
                is_error=is_error,
                duration_ms=duration_ms,
            )
        )
        await self.db.flush()

    async def has_active_run(
        self, conversation_id: UUID, *, stale_after: timedelta = timedelta(minutes=15)
    ) -> bool:
        """A run is active if it is still 'running' and started recently.

        A run left 'running' by a server restart would otherwise block the
        conversation forever; after ``stale_after`` it no longer counts.
        """
        cutoff = datetime.now(timezone.utc) - stale_after
        found = await self.db.scalar(
            select(AgentRun.id)
            .where(
                AgentRun.conversation_id == conversation_id,
                AgentRun.status == "running",
                AgentRun.started_at >= cutoff,
            )
            .limit(1)
        )
        return found is not None

    async def get_run(self, run_id: UUID) -> AgentRun | None:
        return await self.db.get(AgentRun, run_id)

    async def get_trace(self, run_id: UUID) -> tuple[AgentRun, list[ToolCall]] | None:
        run = await self.get_run(run_id)
        if run is None:
            return None
        result = await self.db.execute(
            select(ToolCall).where(ToolCall.run_id == run_id).order_by(ToolCall.seq)
        )
        return run, list(result.scalars().all())

    async def list_runs(self, conversation_id: UUID) -> list[AgentRun]:
        result = await self.db.execute(
            select(AgentRun)
            .where(AgentRun.conversation_id == conversation_id)
            .order_by(AgentRun.started_at)
        )
        return list(result.scalars().all())
