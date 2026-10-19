import uuid
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from anthropic.lib.tools import ToolError

from app.deal_recommendation.agent.context import RunContext
from app.deal_recommendation.agent.loop import AgentLoop, LoopSettings
from app.deal_recommendation.agent.prompt import BUDGET_TEXT, NUDGE_TEXT
from app.deal_recommendation.agent.tools import ToolOutcome


# ── fakes ──────────────────────────────────────────────────────────────────


class Block(SimpleNamespace):
    def to_dict(self):
        return {k: v for k, v in vars(self).items()}


def text(t):
    return Block(type="text", text=t)


def tool_use(name, input=None, id=None):
    return Block(type="tool_use", id=id or f"toolu_{uuid.uuid4().hex[:8]}", name=name, input=input or {})


def turn(*blocks, stop_reason=None, usage=None):
    stop = stop_reason or ("tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn")
    return SimpleNamespace(
        content=list(blocks),
        stop_reason=stop,
        usage=usage or SimpleNamespace(input_tokens=100, output_tokens=10,
                                       cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )


class FakeStream:
    def __init__(self, message):
        self.message = message

    def __aiter__(self):
        async def gen():
            for block in self.message.content:
                if block.type == "text":
                    yield SimpleNamespace(type="text", text=block.text)
        return gen()

    async def get_final_message(self):
        return self.message


class FakeRunner:
    """Mimics the SDK streaming runner over a script of turns (or exceptions)."""

    def __init__(self, script, handlers):
        self.script = script
        self.handlers = handlers
        self.current = None

    def __aiter__(self):
        async def gen():
            while self.script:
                item = self.script.pop(0)
                if isinstance(item, Exception):
                    raise item
                self.current = item
                yield FakeStream(item)
                if not any(b.type == "tool_use" for b in item.content):
                    return
        return gen()

    async def generate_tool_call_response(self):
        results = []
        for block in self.current.content:
            if block.type != "tool_use":
                continue
            try:
                content = await self.handlers[block.name](block.input)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})
            except ToolError as exc:
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": str(exc), "is_error": True})
        return {"role": "user", "content": results}


class FakeExecutor:
    def __init__(self):
        self.calls = []

    async def execute(self, name, tool_input, ctx):
        self.calls.append(name)
        if name == "present_shortlist":
            ctx.shortlist_presented = True
            return ToolOutcome({"presented": 3}, False, "Presented 3 deals")
        return ToolOutcome({"candidates": []}, False, "0 candidates")


class FakeConversations:
    def __init__(self):
        self.rows = [("user", "notes")]

    async def load_history(self, conversation_id):
        return [{"role": r, "content": c} for r, c in self.rows]

    async def append_messages(self, conversation_id, items):
        self.rows.extend(items)


class FakeRuns:
    def __init__(self):
        self.tool_calls = []
        self.finished = None

    async def add_tool_call(self, **kwargs):
        self.tool_calls.append(kwargs)

    async def finish_run(self, run_id, **kwargs):
        self.finished = kwargs


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def build(script_runs, max_tool_calls=12):
    """script_runs: one script (list of turns) per runner the loop will create."""
    events = []

    async def emit(event, data):
        events.append((event, data))

    ctx = RunContext(conversation_id=uuid.uuid4(), run_id=uuid.uuid4(), emit=emit)
    conversations, runs = FakeConversations(), FakeRuns()
    runners = []

    def factory(history, handlers):
        runner = FakeRunner(script_runs.pop(0), handlers)
        runners.append(history)
        return runner

    loop = AgentLoop(
        client=None,
        executor=FakeExecutor(),
        session=FakeSession(),
        conversations=conversations,
        runs=runs,
        settings=LoopSettings(model="claude-sonnet-5-5", effort="high", max_tool_calls=max_tool_calls),
        system_prompt="system",
        runner_factory=factory,
    )
    return loop, ctx, events, conversations, runs, runners


def roles(conversations):
    return [r for r, _ in conversations.rows]


# ── tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_default_factory_request_shape():
    captured = {}

    class Messages:
        def tool_runner(self, **kwargs):
            captured.update(kwargs)
            return FakeRunner([turn(text("hi?"))], {})

    client = SimpleNamespace(beta=SimpleNamespace(messages=Messages()))
    loop, ctx, *_ = build([])
    loop.client = client
    loop.runner_factory = None
    await loop.run(ctx)
    assert captured["model"] == "claude-sonnet-5-5"
    assert captured["stream"] is True
    assert captured["thinking"] == {"type": "adaptive"}
    assert captured["output_config"] == {"effort": "high"}
    assert captured["cache_control"] == {"type": "ephemeral"}
    assert "tool_choice" not in captured
    assert captured["fallbacks"] == "default"
    assert captured["betas"] == ["server-side-fallback-2026-07-01"]
    assert captured["system"] == [{"type": "text", "text": "system"}]
    assert [t.name for t in captured["tools"]] == [
        "update_client_profile", "search_deals", "find_similar_deals",
        "get_deal_details", "present_shortlist",
    ]
    assert {t.name: t.to_dict()["strict"] for t in captured["tools"]} == {
        "update_client_profile": False,
        "search_deals": True,
        "find_similar_deals": False,
        "get_deal_details": True,
        "present_shortlist": True,
    }


@pytest.mark.asyncio
async def test_turns_saved_with_tool_results_together():
    script = [
        turn(text("Searching."), tool_use("search_deals", id="a")),
        turn(tool_use("present_shortlist", id="b")),
        turn(text("Here are five deals.")),
    ]
    loop, ctx, events, conversations, runs, _ = build([script])
    result = await loop.run(ctx)
    assert result.status == "succeeded"
    assert roles(conversations) == ["user", "assistant", "user", "assistant", "user", "assistant"]
    for i, (role, content) in enumerate(conversations.rows):
        if role == "assistant" and isinstance(content, list):
            ids = [b["id"] for b in content if b["type"] == "tool_use"]
            if ids:
                next_role, next_content = conversations.rows[i + 1]
                assert next_role == "user"
                assert [r["tool_use_id"] for r in next_content] == ids
    assert [c["tool_name"] for c in runs.tool_calls] == ["search_deals", "present_shortlist"]
    assert runs.finished["status"] == "succeeded"
    assert events[-1][0] == "run_finished"


@pytest.mark.asyncio
async def test_stream_events_in_order():
    script = [
        turn(text("Looking at budget."), tool_use("search_deals")),
        turn(tool_use("present_shortlist")),
        turn(text("Done.")),
    ]
    loop, ctx, events, *_ = build([script])
    await loop.run(ctx)
    kinds = [e for e, _ in events]
    assert kinds[:4] == ["text_delta", "tool_started", "tool_finished", "tool_started"]
    finished = [d for e, d in events if e == "tool_finished"][0]
    assert finished["summary"] == "0 candidates"
    assert finished["tool"] == "search_deals"
    assert kinds[-2:] == ["text_delta", "run_finished"]


@pytest.mark.asyncio
async def test_nudges_once_when_no_shortlist_and_no_question():
    first = [turn(text("Here are some thoughts."))]
    second = [turn(tool_use("present_shortlist")), turn(text("Done."))]
    loop, ctx, _, conversations, _, runners = build([first, second])
    result = await loop.run(ctx)
    assert result.status == "succeeded"
    nudges = [c for r, c in conversations.rows if r == "user" and c == [{"type": "text", "text": NUDGE_TEXT}]]
    assert len(nudges) == 1
    assert len(runners) == 2


@pytest.mark.asyncio
async def test_only_one_nudge():
    loop, ctx, _, conversations, *_ = build([[turn(text("Hmm."))], [turn(text("Still hmm."))]])
    result = await loop.run(ctx)
    assert result.status == "succeeded"
    nudge = [{"type": "text", "text": NUDGE_TEXT}]
    assert sum(1 for _, c in conversations.rows if c == nudge) == 1


@pytest.mark.asyncio
async def test_clarifying_question_ends_run_without_nudge():
    loop, ctx, _, conversations, runs, runners = build([[turn(text("What budget did they mention?"))]])
    result = await loop.run(ctx)
    assert result.status == "succeeded"
    assert roles(conversations) == ["user", "assistant"]
    assert len(runners) == 1


@pytest.mark.asyncio
async def test_tool_budget_then_capped():
    script = [turn(tool_use("search_deals")) for _ in range(6)]
    loop, ctx, _, conversations, runs, _ = build([script], max_tool_calls=2)
    result = await loop.run(ctx)
    assert result.status == "capped"
    outputs = [c["output"] for c in runs.tool_calls]
    assert outputs[2] == {"error": BUDGET_TEXT}
    assert len(runs.tool_calls) == 5
    # history still valid: last stored row answers the last tool_use
    assert conversations.rows[-1][0] == "user"


@pytest.mark.asyncio
async def test_api_error_marks_failed_and_keeps_history_valid():
    error = anthropic.APIStatusError(
        "overloaded",
        response=httpx.Response(529, request=httpx.Request("POST", "https://api.anthropic.com")),
        body=None,
    )
    script = [turn(tool_use("search_deals")), error]
    loop, ctx, events, conversations, runs, _ = build([script])
    result = await loop.run(ctx)
    assert result.status == "failed"
    assert "overloaded" in result.error
    assert any(e == "error" for e, _ in events)
    assert conversations.rows[-1][0] == "user"
    assert runs.finished["status"] == "failed"


@pytest.mark.asyncio
async def test_refusal_marks_failed():
    loop, ctx, _, conversations, *_ = build([[turn(text(""), stop_reason="refusal")]])
    result = await loop.run(ctx)
    assert result.status == "failed"
    assert result.stop_reason == "refusal"


@pytest.mark.asyncio
async def test_truncated_tool_call_is_not_saved():
    loop, ctx, _, conversations, *_ = build(
        [[turn(tool_use("search_deals"), stop_reason="max_tokens")]]
    )
    result = await loop.run(ctx)
    assert result.status == "failed"
    assert roles(conversations) == ["user"]


@pytest.mark.asyncio
async def test_usage_accumulates_across_turns():
    script = [turn(tool_use("present_shortlist")), turn(text("Done."))]
    loop, ctx, *_ = build([script])
    result = await loop.run(ctx)
    assert result.usage.input_tokens == 200
    assert result.usage.output_tokens == 20
    assert result.iterations == 2


# ── final-review fixes ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_nudge_is_saved_as_user_text_never_system():
    first = [turn(text("No deals fit; here is why."))]
    second = [turn(tool_use("present_shortlist")), turn(text("Done."))]
    loop, ctx, _, conversations, _, runners = build([first, second])
    await loop.run(ctx)
    assert "system" not in roles(conversations)
    nudge = {"role": "user", "content": [{"type": "text", "text": NUDGE_TEXT}]}
    assert runners[1][-1] == nudge
    # placement: every user row follows an assistant row or is first
    for (prev, _), (role, _) in zip(conversations.rows, conversations.rows[1:]):
        assert prev != role


@pytest.mark.asyncio
async def test_question_in_last_paragraph_counts_as_clarifying_question():
    reply = "What budget did they mention?\n\nPaste the full summary and I'll start."
    loop, ctx, _, conversations, _, runners = build([[turn(text(reply))], [turn(text("x"))]])
    result = await loop.run(ctx)
    assert result.status == "succeeded"
    assert len(runners) == 1


@pytest.mark.asyncio
async def test_empty_refusal_is_not_saved():
    loop, ctx, _, conversations, *_ = build([[turn(stop_reason="refusal")]])
    result = await loop.run(ctx)
    assert result.status == "failed"
    assert roles(conversations) == ["user"]


class ClosableRunner(FakeRunner):
    closed = False

    async def close(self):
        ClosableRunner.closed = True


@pytest.mark.asyncio
async def test_runner_closed_when_run_stops_early():
    loop, ctx, *_ = build([])
    ClosableRunner.closed = False
    loop.runner_factory = lambda history, handlers: ClosableRunner(
        [turn(tool_use("search_deals"), stop_reason="max_tokens")], handlers
    )
    await loop.run(ctx)
    assert ClosableRunner.closed is True
