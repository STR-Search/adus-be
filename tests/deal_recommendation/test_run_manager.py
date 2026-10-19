import asyncio
import json
import uuid

import pytest

from app.deal_recommendation.agent.loop import RunResult
from app.deal_recommendation.services.run_manager import (
    ConversationBusy,
    PreparedRun,
    RunManager,
    format_sse,
)


class SlowLoop:
    """Emits a few events with pauses, then finishes."""

    def __init__(self, finished):
        self.finished = finished

    async def run(self, ctx):
        await ctx.emit("text_delta", {"text": "Looking"})
        await asyncio.sleep(0.05)
        await ctx.emit("text_delta", {"text": " at deals"})
        await asyncio.sleep(0.05)
        self.finished.append(ctx.run_id)
        await ctx.emit("run_finished", {"status": "succeeded"})
        return RunResult(status="succeeded", stop_reason="end_turn", iterations=1)


class FakeManager(RunManager):
    def __init__(self, busy=False):
        super().__init__(session_factory=None)
        self.busy = busy
        self.finished = []

    async def _prepare(self, *, conversation_id, text, user_id):
        if self.busy:
            raise ConversationBusy()
        return PreparedRun(
            run_id=uuid.uuid4(), down_payment_pct=None, interest_rate=None, already_shown_ids=set()
        )

    async def _execute(self, conversation_id, prepared, ctx):
        return await SlowLoop(self.finished).run(ctx)


def _events(chunks):
    return [chunk.split("\n", 1)[0].removeprefix("event: ") for chunk in chunks]


@pytest.mark.asyncio
async def test_stream_yields_run_started_then_loop_events():
    manager = FakeManager()
    stream = await manager.start(conversation_id=uuid.uuid4(), text="notes", user_id=1)
    chunks = [chunk async for chunk in stream]
    assert _events(chunks) == ["run_started", "text_delta", "text_delta", "run_finished"]


@pytest.mark.asyncio
async def test_disconnect_does_not_cancel_run():
    manager = FakeManager()
    conversation_id = uuid.uuid4()
    stream = await manager.start(conversation_id=conversation_id, text="notes", user_id=1)
    first = await stream.__anext__()
    assert first.startswith("event: run_started")
    await stream.aclose()  # browser went away
    await manager.wait(conversation_id)
    assert len(manager.finished) == 1


@pytest.mark.asyncio
async def test_busy_when_task_running():
    manager = FakeManager()
    conversation_id = uuid.uuid4()
    stream = await manager.start(conversation_id=conversation_id, text="notes", user_id=1)
    with pytest.raises(ConversationBusy):
        await manager.start(conversation_id=conversation_id, text="again", user_id=1)
    async for _ in stream:
        pass
    await manager.wait(conversation_id)
    # finished: a new run may start
    again = await manager.start(conversation_id=conversation_id, text="again", user_id=1)
    async for _ in again:
        pass


@pytest.mark.asyncio
async def test_busy_from_database_check():
    with pytest.raises(ConversationBusy):
        await FakeManager(busy=True).start(conversation_id=uuid.uuid4(), text="x", user_id=1)


@pytest.mark.asyncio
async def test_run_to_completion_returns_result():
    result = await FakeManager().run_to_completion(
        conversation_id=uuid.uuid4(), text="notes", user_id=None
    )
    assert result.status == "succeeded"


def test_format_sse():
    chunk = format_sse("text_delta", {"text": "hi"})
    assert chunk == 'event: text_delta\ndata: {"text": "hi"}\n\n'
    assert json.loads(format_sse("x", {"n": 1}).split("data: ")[1]) == {"n": 1}


class SlowPrepareManager(FakeManager):
    async def _prepare(self, *, conversation_id, text, user_id):
        await asyncio.sleep(0.05)  # both requests are inside _prepare at once
        return await super()._prepare(conversation_id=conversation_id, text=text, user_id=user_id)


@pytest.mark.asyncio
async def test_simultaneous_starts_only_one_wins():
    manager = SlowPrepareManager()
    conversation_id = uuid.uuid4()
    results = await asyncio.gather(
        manager.start(conversation_id=conversation_id, text="a", user_id=1),
        manager.start(conversation_id=conversation_id, text="b", user_id=1),
        return_exceptions=True,
    )
    assert sum(isinstance(r, ConversationBusy) for r in results) == 1
    stream = next(r for r in results if not isinstance(r, Exception))
    async for _ in stream:
        pass


@pytest.mark.asyncio
async def test_failed_prepare_releases_the_conversation():
    manager = FakeManager(busy=True)
    conversation_id = uuid.uuid4()
    with pytest.raises(ConversationBusy):
        await manager.start(conversation_id=conversation_id, text="a", user_id=1)
    manager.busy = False
    stream = await manager.start(conversation_id=conversation_id, text="b", user_id=1)
    async for _ in stream:
        pass
