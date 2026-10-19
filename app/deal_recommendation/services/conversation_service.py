"""Read side of conversations: what the UI shows for a saved thread."""

from uuid import UUID

from app.deal_recommendation.models import AgentRun, Message
from app.deal_recommendation.repositories.conversation_repository import (
    ConversationRepository,
)
from app.deal_recommendation.repositories.recommendation_repository import (
    RecommendationRepository,
)
from app.deal_recommendation.repositories.run_repository import RunRepository

_RUN_COLUMNS = (
    "id",
    "conversation_id",
    "model",
    "effort",
    "status",
    "stop_reason",
    "iterations",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "cost_usd",
    "error",
    "started_at",
    "finished_at",
)


def _is_user_text(message: Message) -> bool:
    return message.role == "user" and isinstance(message.content, str)


def _assistant_text(messages: list[Message]) -> str:
    parts = []
    for message in messages:
        if message.role != "assistant" or not isinstance(message.content, list):
            continue
        text = "".join(b.get("text", "") for b in message.content if b.get("type") == "text")
        if text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts)


class ConversationService:
    def __init__(
        self,
        conversations: ConversationRepository,
        runs: RunRepository,
        recommendations: RecommendationRepository,
    ):
        self.conversations = conversations
        self.runs = runs
        self.recommendations = recommendations

    async def create(self, *, title: str | None, user_id: int | None, model: str):
        return await self.conversations.create(
            title=title, created_by_user_id=user_id, model=model
        )

    async def list(self):
        return await self.conversations.list_recent()

    async def exists(self, conversation_id: UUID) -> bool:
        return await self.conversations.get(conversation_id) is not None

    async def get(self, conversation_id: UUID) -> dict | None:
        conversation = await self.conversations.get(conversation_id)
        if conversation is None:
            return None
        messages = await self.conversations.list_messages(conversation_id)
        runs_by_message: dict[int, AgentRun] = {
            run.user_message_id: run for run in await self.runs.list_runs(conversation_id)
        }
        profiles_by_run = {
            p.run_id: p.profile for p in await self.recommendations.list_profiles(conversation_id)
        }
        cards_by_run: dict = {}
        for rec in await self.recommendations.list_for_conversation(conversation_id):
            cards_by_run.setdefault(rec.run_id, []).append(rec)

        # Split the history at each typed user message; everything until the
        # next one (assistant turns, tool results, nudges) belongs to that turn.
        groups: list[tuple[Message, list[Message]]] = []
        for message in messages:
            if _is_user_text(message):
                groups.append((message, []))
            elif groups:
                groups[-1][1].append(message)

        turns = []
        for user_message, rest in groups:
            run = runs_by_message.get(user_message.id)
            steps, cards = [], []
            if run is not None:
                trace = await self.runs.get_trace(run.id)
                steps = [
                    {"tool": c.tool_name, "is_error": c.is_error, "duration_ms": c.duration_ms}
                    for c in (trace[1] if trace else [])
                ]
                cards = [
                    {
                        "rank": r.rank,
                        "underwriting_id": r.underwriting_id,
                        "match_score": r.match_score,
                        "why": r.why,
                        "matched": list(r.matched or []),
                        "missed": list(r.missed or []),
                        "snapshot": r.snapshot,
                    }
                    for r in sorted(cards_by_run.get(run.id, []), key=lambda r: r.rank)
                ]
            turns.append(
                {
                    "user_text": user_message.content,
                    "run": (
                        {"id": run.id, "status": run.status, "cost_usd": run.cost_usd, "error": run.error}
                        if run
                        else None
                    ),
                    "assistant_text": _assistant_text(rest),
                    "tool_steps": steps,
                    "profile": profiles_by_run.get(run.id) if run else None,
                    "cards": cards,
                }
            )
        return {"id": conversation.id, "title": conversation.title, "turns": turns}

    async def trace(self, run_id: UUID) -> dict | None:
        found = await self.runs.get_trace(run_id)
        if found is None:
            return None
        run, calls = found
        return {
            "run": {column: getattr(run, column) for column in _RUN_COLUMNS},
            "tool_calls": [
                {
                    "seq": c.seq,
                    "tool_name": c.tool_name,
                    "input": c.input,
                    "output": c.output,
                    "is_error": c.is_error,
                    "duration_ms": c.duration_ms,
                }
                for c in calls
            ],
        }
