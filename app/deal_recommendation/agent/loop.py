"""One agent run: the SDK Tool Runner does the looping, this code wraps it.

The Tool Runner calls Claude, runs the tools Claude asks for, feeds the results
back, and repeats until Claude stops calling tools. Around it, this module:
  1. forwards the streamed text to the UI,
  2. saves every turn (an assistant turn and its tool results in one commit, so
     the stored history never has an unanswered tool call),
  3. stops runaway runs via the tool budget (enforced in runner_tools), and
  4. if Claude ends without a shortlist or a question, restarts once with a nudge.

The nudge is saved as a user message: the API only accepts a mid-conversation
system message right after a user turn, and the history is replayed verbatim.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.deal_recommendation.agent.context import RunContext
from app.deal_recommendation.agent.prompt import NUDGE_TEXT
from app.deal_recommendation.agent.runner_tools import (
    ToolHandler,
    build_tool_handlers,
    to_sdk_tools,
)
from app.deal_recommendation.agent.tools import ToolExecutor
from app.deal_recommendation.repositories.conversation_repository import (
    ConversationRepository,
)
from app.deal_recommendation.repositories.run_repository import RunRepository, RunUsage

FALLBACK_BETA = "server-side-fallback-2026-07-01"

RunnerFactory = Callable[[list[dict], dict[str, ToolHandler]], Any]


@dataclass
class LoopSettings:
    model: str
    effort: str
    max_tool_calls: int
    max_tokens: int = 64000


@dataclass
class RunResult:
    status: str  # succeeded | failed | capped
    stop_reason: str | None
    iterations: int
    usage: RunUsage = field(default_factory=RunUsage)
    error: str | None = None


class _RunFailed(Exception):
    def __init__(self, message: str, stop_reason: str | None = None):
        super().__init__(message)
        self.stop_reason = stop_reason


def _text_of(blocks: list[dict]) -> str:
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


def _asks_question(text: str) -> bool:
    """True when the reply ends by asking the team member something.

    Looks at the last two paragraphs, so "What budget?\n\nPaste it and I'll
    start." still counts as a question.
    """
    paragraphs = [p for p in text.strip().split("\n\n") if p.strip()]
    return any("?" in p for p in paragraphs[-2:])


async def _close(runner: Any) -> None:
    """Release the runner's open stream/HTTP connection on every exit path."""
    close = getattr(runner, "close", None)
    if close is not None:
        await close()


@dataclass
class _RunState:
    usage: RunUsage = field(default_factory=RunUsage)
    iterations: int = 0
    stop_reason: str | None = None


def _asks_question(text: str) -> bool:
    """True when the reply ends by asking the team member something.

    Looks at the last two paragraphs, so "What budget?\n\nPaste it and I'll
    start." still counts as a question.
    """
    paragraphs = [p for p in text.strip().split("\n\n") if p.strip()]
    return any("?" in p for p in paragraphs[-2:])


class AgentLoop:
    def __init__(
        self,
        client: Any,
        executor: ToolExecutor,
        session: AsyncSession,
        conversations: ConversationRepository,
        runs: RunRepository,
        settings: LoopSettings,
        system_prompt: str,
        runner_factory: RunnerFactory | None = None,
    ):
        self.client = client
        self.executor = executor
        self.session = session
        self.conversations = conversations
        self.runs = runs
        self.settings = settings
        self.system_prompt = system_prompt
        self.runner_factory = runner_factory

    def _sdk_runner(self, history: list[dict], handlers: dict[str, ToolHandler]):
        return self.client.beta.messages.tool_runner(
            model=self.settings.model,
            max_tokens=self.settings.max_tokens,
            system=[{"type": "text", "text": self.system_prompt}],
            tools=to_sdk_tools(handlers),
            messages=history,
            stream=True,
            thinking={"type": "adaptive"},
            output_config={"effort": self.settings.effort},
            cache_control={"type": "ephemeral"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )

    async def run(self, ctx: RunContext) -> RunResult:
        handlers = build_tool_handlers(
            self.executor, ctx, self.runs, self.settings.max_tool_calls
        )
        factory = self.runner_factory or self._sdk_runner
        state = _RunState()
        nudged = False
        status, error = "succeeded", None

        try:
            while True:
                history = await self.conversations.load_history(ctx.conversation_id)
                runner = factory(history, handlers)
                try:
                    final_text = await self._drive(ctx, runner, state)
                finally:
                    await _close(runner)
                if ctx.budget_exhausted:
                    status = "capped"
                    break
                if ctx.shortlist_presented or _asks_question(final_text) or nudged:
                    break
                await self._save(ctx, [("user", [{"type": "text", "text": NUDGE_TEXT}])])
                nudged = True
        except _RunFailed as exc:
            status, error = "failed", str(exc)
            state.stop_reason = exc.stop_reason or state.stop_reason
        except Exception as exc:  # noqa: BLE001 — API errors and bugs both end the run cleanly
            logger.exception("deal_recommendation.run_failed", run_id=str(ctx.run_id))
            await self.session.rollback()
            status, error = "failed", str(exc) or type(exc).__name__

        if error is not None:
            await ctx.emit("error", {"message": error})
        await self.runs.finish_run(
            ctx.run_id,
            status=status,
            stop_reason=state.stop_reason,
            iterations=state.iterations,
            usage=state.usage,
            error=error,
        )
        await self.session.commit()
        await ctx.emit(
            "run_finished",
            {
                "status": status,
                "usage": state.usage.as_dict(),
                "cost_usd": str(state.usage.cost_usd()),
            },
        )
        return RunResult(
            status=status,
            stop_reason=state.stop_reason,
            iterations=state.iterations,
            usage=state.usage,
            error=error,
        )

    async def _drive(self, ctx: RunContext, runner: Any, state: "_RunState") -> str:
        """Consume one runner; save each turn. Returns the last text-only reply."""
        final_text = ""
        async for stream in runner:
            async for event in stream:
                if event.type == "text":
                    await ctx.emit("text_delta", {"text": event.text})
            message = await stream.get_final_message()
            state.iterations += 1
            state.usage.add(message.usage)
            state.stop_reason = message.stop_reason
            blocks = [block.to_dict() for block in message.content]
            has_tool_use = any(b.get("type") == "tool_use" for b in blocks)

            if state.stop_reason == "max_tokens" and has_tool_use:
                # A truncated tool call is never run or saved.
                raise _RunFailed("Reply was cut off mid tool call", state.stop_reason)
            if state.stop_reason == "refusal":
                # An empty assistant message would make every later request fail.
                if blocks and not has_tool_use:
                    await self._save(ctx, [("assistant", blocks)])
                raise _RunFailed("Claude declined this request", state.stop_reason)

            if has_tool_use:
                response = await runner.generate_tool_call_response()
                items = [("assistant", blocks)]
                if response is not None:
                    items.append(("user", list(response["content"])))
                await self._save(ctx, items)
            elif blocks:
                await self._save(ctx, [("assistant", blocks)])
                final_text = _text_of(blocks)

            if ctx.budget_exhausted:
                break
        return final_text

    async def _save(self, ctx: RunContext, items: list[tuple[str, Any]]) -> None:
        await self.conversations.append_messages(ctx.conversation_id, items)
        await self.session.commit()
