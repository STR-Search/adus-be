import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.deal_recommendation.services.conversation_service import ConversationService

CONV = uuid.uuid4()
RUN1, RUN2 = uuid.uuid4(), uuid.uuid4()


def msg(id, role, content):
    return SimpleNamespace(id=id, role=role, content=content)


class FakeConversations:
    async def get(self, conversation_id):
        return SimpleNamespace(id=CONV, title="Rav & Anna") if conversation_id == CONV else None

    async def list_messages(self, conversation_id):
        return [
            msg(1, "user", "Fathom notes"),
            msg(2, "assistant", [{"type": "thinking", "thinking": ""},
                                 {"type": "text", "text": "Checking budget."},
                                 {"type": "tool_use", "id": "t1", "name": "search_deals", "input": {}}]),
            msg(3, "user", [{"type": "tool_result", "tool_use_id": "t1", "content": "{}"}]),
            msg(4, "assistant", [{"type": "text", "text": "Here are 3 deals."}]),
            msg(5, "user", "More cash flow"),
            msg(6, "assistant", [{"type": "text", "text": "Updated."}]),
        ]


class FakeRuns:
    async def list_runs(self, conversation_id):
        return [
            SimpleNamespace(id=RUN1, user_message_id=1, status="succeeded", cost_usd=Decimal("0.4"), error=None),
            SimpleNamespace(id=RUN2, user_message_id=5, status="failed", cost_usd=None, error="boom"),
        ]

    async def get_trace(self, run_id):
        calls = [SimpleNamespace(tool_name="search_deals", is_error=False, duration_ms=120)]
        return (None, calls if run_id == RUN1 else [])


class FakeRecommendations:
    async def list_profiles(self, conversation_id):
        return [SimpleNamespace(run_id=RUN1, profile={"client_label": "Rav & Anna"})]

    async def list_for_conversation(self, conversation_id):
        return [
            SimpleNamespace(run_id=RUN1, rank=2, underwriting_id=9, match_score=None, why="b",
                            matched=[], missed=[], snapshot={}),
            SimpleNamespace(run_id=RUN1, rank=1, underwriting_id=7, match_score=Decimal("88"), why="a",
                            matched=["tax"], missed=None, snapshot={"city": "Austin"}),
        ]


def service():
    return ConversationService(FakeConversations(), FakeRuns(), FakeRecommendations())


@pytest.mark.asyncio
async def test_turns_split_at_typed_user_messages():
    detail = await service().get(CONV)
    assert [t["user_text"] for t in detail["turns"]] == ["Fathom notes", "More cash flow"]
    first, second = detail["turns"]
    assert first["assistant_text"] == "Checking budget.\n\nHere are 3 deals."
    assert first["tool_steps"] == [{"tool": "search_deals", "is_error": False, "duration_ms": 120}]
    assert [c["underwriting_id"] for c in first["cards"]] == [7, 9]
    assert first["cards"][0]["missed"] == []
    assert first["profile"] == {"client_label": "Rav & Anna"}
    assert second["run"]["status"] == "failed" and second["run"]["error"] == "boom"
    assert second["cards"] == [] and second["profile"] is None


@pytest.mark.asyncio
async def test_missing_conversation_returns_none():
    assert await service().get(uuid.uuid4()) is None
