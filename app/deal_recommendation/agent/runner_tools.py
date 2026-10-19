"""Wrap the ToolExecutor as Tool Runner tools.

The SDK's Tool Runner calls these functions when Claude asks for a tool. Each
wrapper streams a start/finish event to the UI, records the call in the trace,
and enforces the per-run tool budget.
"""

import json
import time
from collections.abc import Awaitable, Callable, Mapping

from anthropic.lib.tools import BetaAsyncFunctionTool, ToolError

from app.deal_recommendation.agent.context import RunContext
from app.deal_recommendation.agent.prompt import BUDGET_TEXT
from app.deal_recommendation.agent.tools import (
    TOOL_DEFINITIONS,
    TOOL_PROGRESS_LABELS,
    ToolExecutor,
    ToolOutcome,
)
from app.deal_recommendation.repositories.run_repository import RunRepository

ToolHandler = Callable[[dict], Awaitable[str]]

# Calls allowed past the budget (each answered with BUDGET_TEXT) before the run stops.
BUDGET_GRACE = 3
_ALWAYS_ALLOWED = {"present_shortlist"}


def build_tool_handlers(
    executor: ToolExecutor,
    ctx: RunContext,
    runs: RunRepository,
    max_tool_calls: int,
) -> dict[str, ToolHandler]:
    def make(name: str) -> ToolHandler:
        async def handle(tool_input: dict) -> str:
            ctx.tool_calls += 1
            seq = ctx.tool_calls
            await ctx.emit(
                "tool_started", {"tool": name, "label": TOOL_PROGRESS_LABELS[name]}
            )
            started = time.monotonic()
            if seq > max_tool_calls and name not in _ALWAYS_ALLOWED:
                outcome = ToolOutcome({"error": BUDGET_TEXT}, True, "Tool budget reached")
            else:
                try:
                    outcome = await executor.execute(name, tool_input, ctx)
                except Exception as exc:  # a tool bug must not kill the run
                    outcome = ToolOutcome({"error": f"Tool failed: {exc}"}, True, "Tool failed")
            if seq >= max_tool_calls + BUDGET_GRACE:
                ctx.budget_exhausted = True
            duration_ms = int((time.monotonic() - started) * 1000)
            await runs.add_tool_call(
                run_id=ctx.run_id,
                seq=seq,
                tool_use_id=None,
                tool_name=name,
                input=tool_input,
                output=outcome.content,
                is_error=outcome.is_error,
                duration_ms=duration_ms,
            )
            await ctx.emit(
                "tool_finished",
                {
                    "tool": name,
                    "summary": outcome.summary,
                    "is_error": outcome.is_error,
                    "duration_ms": duration_ms,
                },
            )
            payload = json.dumps(outcome.content, default=str)
            if outcome.is_error:
                raise ToolError(payload)
            return payload

        return handle

    return {definition["name"]: make(definition["name"]) for definition in TOOL_DEFINITIONS}


def to_sdk_tools(handlers: Mapping[str, ToolHandler]) -> list[BetaAsyncFunctionTool]:
    """Tool Runner tools that send our strict schemas and call our handlers."""
    tools = []
    for definition in TOOL_DEFINITIONS:
        tools.append(
            BetaAsyncFunctionTool(
                _keyword_adapter(handlers[definition["name"]]),
                name=definition["name"],
                description=definition["description"],
                input_schema=definition["input_schema"],
                strict=definition["strict"],
            )
        )
    return tools


def _keyword_adapter(handler: ToolHandler):
    """The runner calls tools as ``func(**input)``; our handlers take one dict."""

    async def call(**tool_input) -> str:
        return await handler(tool_input)

    return call
