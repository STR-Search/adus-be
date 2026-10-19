"""Starts agent runs in the background and streams their events as SSE.

The run itself is an asyncio task with its own DB session, so it keeps going —
and keeps saving — if the browser disconnects. The SSE stream only reads the
task's event queue; closing the stream never cancels the task.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from anthropic import AsyncAnthropic

from app.core.config import get_config
from app.core.database import AsyncSessionLocal
from app.core.logger import logger
from app.core.reference_data.repository import ReferenceDataRepository
from app.core.reference_data.service import ReferenceDataService
from app.deal_recommendation.agent.context import PoolOverride, RunContext
from app.deal_recommendation.agent.loop import AgentLoop, LoopSettings, RunResult
from app.deal_recommendation.agent.prompt import build_system_prompt
from app.deal_recommendation.agent.tools import ToolExecutor
from app.deal_recommendation.repositories.conversation_repository import (
    ConversationRepository,
)
from app.deal_recommendation.repositories.recommendation_repository import (
    RecommendationRepository,
)
from app.deal_recommendation.repositories.run_repository import RunRepository
from app.iron_bank.services.deal_catalog_service import DealCatalogService

_TERMINAL_EVENTS = {"run_finished"}
_TITLE_CHARS = 60


class ConversationBusy(Exception):
    """A run is already in progress for this conversation."""


@dataclass
class PreparedRun:
    run_id: UUID
    down_payment_pct: Decimal | None
    interest_rate: Decimal | None
    already_shown_ids: set[int]


def format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _default_title(text: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first_line[:_TITLE_CHARS] or "Untitled"


class RunManager:
    def __init__(self, session_factory=AsyncSessionLocal, client: Any = None):
        self.session_factory = session_factory
        self._client = client
        self._tasks: dict[UUID, asyncio.Task] = {}
        self._starting: set[UUID] = set()

    @property
    def client(self):
        if self._client is None:
            self._client = AsyncAnthropic(api_key=get_config().ANTHROPIC_API_KEY or None)
        return self._client

    def is_running(self, conversation_id: UUID) -> bool:
        task = self._tasks.get(conversation_id)
        return task is not None and not task.done()

    async def wait(self, conversation_id: UUID) -> None:
        task = self._tasks.get(conversation_id)
        if task is not None:
            await asyncio.shield(task)

    async def start(
        self,
        *,
        conversation_id: UUID,
        text: str,
        user_id: int | None,
        pool_override: PoolOverride | None = None,
    ) -> AsyncIterator[str]:
        """Prepare and launch a run; returns the SSE stream of its events.

        Raises ConversationBusy before anything is written if a run is going.
        """
        if conversation_id in self._starting or self.is_running(conversation_id):
            raise ConversationBusy()
        # Claimed before the first await, so a second request arriving while
        # this one is still preparing is refused rather than racing it.
        self._starting.add(conversation_id)
        try:
            prepared = await self._prepare(
                conversation_id=conversation_id, text=text, user_id=user_id
            )
        except BaseException:
            self._starting.discard(conversation_id)
            raise
        queue: asyncio.Queue = asyncio.Queue()

        async def emit(event: str, data: dict) -> None:
            queue.put_nowait((event, data))

        ctx = RunContext(
            conversation_id=conversation_id,
            run_id=prepared.run_id,
            down_payment_pct=prepared.down_payment_pct,
            interest_rate=prepared.interest_rate,
            already_shown_ids=prepared.already_shown_ids,
            pool_override=pool_override,
            emit=emit,
        )
        task = asyncio.create_task(self._run_safely(conversation_id, prepared, ctx, queue))
        self._tasks[conversation_id] = task
        self._starting.discard(conversation_id)
        task.add_done_callback(lambda t: self._forget(conversation_id, t))
        return self._stream(prepared.run_id, queue)

    async def run_to_completion(
        self,
        *,
        conversation_id: UUID,
        text: str,
        user_id: int | None,
        pool_override: PoolOverride | None = None,
    ) -> RunResult:
        stream = await self.start(
            conversation_id=conversation_id,
            text=text,
            user_id=user_id,
            pool_override=pool_override,
        )
        task = self._tasks[conversation_id]
        async for _ in stream:
            pass
        return await task

    def _forget(self, conversation_id: UUID, task: asyncio.Task) -> None:
        if self._tasks.get(conversation_id) is task:
            del self._tasks[conversation_id]

    async def _stream(self, run_id: UUID, queue: asyncio.Queue) -> AsyncIterator[str]:
        yield format_sse("run_started", {"run_id": str(run_id)})
        while True:
            event, data = await queue.get()
            yield format_sse(event, data)
            if event in _TERMINAL_EVENTS:
                return

    async def _run_safely(self, conversation_id, prepared, ctx, queue) -> RunResult:
        try:
            return await self._execute(conversation_id, prepared, ctx)
        except Exception as exc:  # the loop handles its own errors; this is a last resort
            logger.exception("deal_recommendation.run_crashed", run_id=str(prepared.run_id))
            queue.put_nowait(("error", {"message": str(exc)}))
            queue.put_nowait(("run_finished", {"status": "failed"}))
            return RunResult(status="failed", stop_reason=None, iterations=0, error=str(exc))

    async def _prepare(self, *, conversation_id: UUID, text: str, user_id: int | None) -> PreparedRun:
        async with self.session_factory() as session:
            conversations = ConversationRepository(session)
            runs = RunRepository(session)
            if await runs.has_active_run(conversation_id):
                raise ConversationBusy()
            conversation = await conversations.get(conversation_id)
            if conversation is not None and not conversation.title:
                await conversations.set_title(conversation_id, _default_title(text))
            [message] = await conversations.append_messages(conversation_id, [("user", text)])
            config = get_config()
            run = await runs.create_run(
                conversation_id=conversation_id,
                user_message_id=message.id,
                model=config.DEAL_REC_MODEL,
                effort=config.DEAL_REC_EFFORT,
            )
            profile = await RecommendationRepository(session).latest_profile(conversation_id) or {}
            await session.commit()
        financing = profile.get("financing") or {}
        return PreparedRun(
            run_id=run.id,
            down_payment_pct=_decimal(financing.get("down_payment_pct")),
            interest_rate=_decimal(financing.get("interest_rate")),
            already_shown_ids=set(profile.get("already_shown_ids") or []),
        )

    async def _execute(self, conversation_id: UUID, prepared: PreparedRun, ctx: RunContext) -> RunResult:
        config = get_config()
        async with self.session_factory() as session:
            tag_options = await ReferenceDataService(
                ReferenceDataRepository(session)
            ).get_reference_data(domain="iron_bank")
            loop = AgentLoop(
                client=self.client,
                executor=ToolExecutor(
                    DealCatalogService.for_session(session),
                    RecommendationRepository(session),
                ),
                session=session,
                conversations=ConversationRepository(session),
                runs=RunRepository(session),
                settings=LoopSettings(
                    model=config.DEAL_REC_MODEL,
                    effort=config.DEAL_REC_EFFORT,
                    max_tool_calls=config.DEAL_REC_MAX_TOOL_CALLS,
                ),
                system_prompt=build_system_prompt(
                    {
                        set_code: [option.key for option in options]
                        for set_code, options in tag_options.options.items()
                    }
                ),
            )
            return await loop.run(ctx)


run_manager = RunManager()
