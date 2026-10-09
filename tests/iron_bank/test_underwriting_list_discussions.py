"""`discussion` summaries on the underwritings list (normal and simulation).

Uses the real DiscussionService over the in-memory discussions repository,
so counts come from the same counter logic the comment routes maintain.
"""

from datetime import timedelta

import pytest

from app.core.discussions.enums import SubjectType
from app.core.discussions.service import DiscussionService
from app.iron_bank.services.get_underwriting_service import GetUnderwritingService
from app.iron_bank.services.simulate_underwritings_service import (
    SimulateUnderwritingsService,
)
from tests.core.discussions.conftest import (
    SAM,
    FakeDiscussionRepository,
    FakeUserLookup,
    doc,
    para,
    text,
)
from tests.iron_bank.test_get_underwriting_service import (
    FakeListRepository,
    FakeUnderwritingRepository,
    _underwriting,
)
from tests.iron_bank.test_simulate_underwritings_service import (
    FakeSimulationRepository,
    _item,
    _row,
)

EMPTY = {"thread_id": None, "comment_count": 0, "last_comment_at": None}


class CountingThreadRepository:
    def __init__(self, links: dict[int, int]):
        self.links = links
        self.calls: list[tuple[list[int], str]] = []

    async def get_thread_ids(self, underwriting_ids, kind):
        self.calls.append((list(underwriting_ids), kind))
        return {u: t for u, t in self.links.items() if u in underwriting_ids}


class Discussions:
    """Real DiscussionService + fake repository, with helpers to seed data."""

    def __init__(self):
        self.repo = FakeDiscussionRepository()
        self.service = DiscussionService(self.repo, FakeUserLookup([SAM]))
        self.summary_calls: list[list[int]] = []
        original = self.service.get_summaries

        async def counting_get_summaries(thread_ids):
            self.summary_calls.append(list(thread_ids))
            return await original(thread_ids)

        self.service.get_summaries = counting_get_summaries

    async def thread_with_comments(self, n: int) -> int:
        thread_id = await self.service.create_thread(SubjectType.UNDERWRITING, SAM.id)
        for _ in range(n):
            self.repo.tick()
            await self.service.create_comment(
                thread_id,
                author_user_id=SAM.id,
                body_version=1,
                body=doc(para(text("x"))),
            )
        return thread_id


def list_item(id):
    item = _underwriting()
    item.id = id
    item.is_automated = False
    return item


@pytest.fixture
def discussions():
    return Discussions()


@pytest.mark.asyncio
async def test_list_rows_get_summaries_in_two_queries(discussions):
    busy = await discussions.thread_with_comments(3)
    quiet = await discussions.thread_with_comments(1)
    # A thread whose only comment was deleted: thread exists, count is 0.
    deleted = await discussions.service.list_comments(quiet)
    await discussions.service.delete_comment(deleted.items[0].id, user_id=SAM.id)

    threads = CountingThreadRepository({7: busy, 8: quiet})
    service = GetUnderwritingService(
        FakeListRepository([list_item(7), list_item(8), list_item(9)]),
        thread_repository=threads,
        discussion_service=discussions.service,
    )

    result = await service.get_all(page=1, page_size=25)

    assert threads.calls == [([7, 8, 9], "general")]
    assert discussions.summary_calls == [[busy, quiet]]

    by_id = {row.id: row.model_dump(mode="json")["discussion"] for row in result.data}
    busy_thread = discussions.repo.threads[busy]
    assert by_id[7] == {
        "thread_id": busy,
        "comment_count": 3,
        "last_comment_at": busy_thread.last_comment_at.isoformat().replace(
            "+00:00", "Z"
        ),
    }
    assert by_id[8] == {"thread_id": quiet, "comment_count": 0, "last_comment_at": None}
    assert by_id[9] == EMPTY


@pytest.mark.asyncio
async def test_last_comment_at_tracks_newest(discussions):
    thread_id = await discussions.thread_with_comments(2)
    service = GetUnderwritingService(
        FakeListRepository([list_item(7)]),
        thread_repository=CountingThreadRepository({7: thread_id}),
        discussion_service=discussions.service,
    )
    row = (await service.get_all(page=1, page_size=25)).data[0]
    newest = max(c.created_at for c in discussions.repo.comments.values())
    assert row.discussion.last_comment_at == newest
    assert newest - min(
        c.created_at for c in discussions.repo.comments.values()
    ) == timedelta(seconds=1)


@pytest.mark.asyncio
async def test_empty_page_makes_no_queries(discussions):
    threads = CountingThreadRepository({})
    service = GetUnderwritingService(
        FakeListRepository([]),
        thread_repository=threads,
        discussion_service=discussions.service,
    )
    result = await service.get_all(page=1, page_size=25)
    assert result.data == []
    assert threads.calls == [] and discussions.summary_calls == []


@pytest.mark.asyncio
async def test_page_without_threads_skips_thread_read(discussions):
    service = GetUnderwritingService(
        FakeListRepository([list_item(7)]),
        thread_repository=CountingThreadRepository({}),
        discussion_service=discussions.service,
    )
    result = await service.get_all(page=1, page_size=25)
    assert result.data[0].model_dump(mode="json")["discussion"] == EMPTY
    assert discussions.repo.threads == {}


@pytest.mark.asyncio
async def test_single_get_has_no_discussion_key(discussions):
    thread_id = await discussions.thread_with_comments(1)
    threads = CountingThreadRepository({42: thread_id})
    service = GetUnderwritingService(
        FakeUnderwritingRepository(_underwriting()),
        thread_repository=threads,
        discussion_service=discussions.service,
    )
    result = await service.get(42)
    assert "discussion" not in result.model_dump(mode="json")
    assert threads.calls == []


@pytest.mark.asyncio
async def test_without_discussion_deps_key_is_absent():
    service = GetUnderwritingService(FakeListRepository([list_item(7)]))
    result = await service.get_all(page=1, page_size=25)
    assert "discussion" not in result.data[0].model_dump(mode="json")


@pytest.mark.asyncio
async def test_simulation_list_rows_get_summaries(discussions):
    thread_id = await discussions.thread_with_comments(2)
    threads = CountingThreadRepository({1: thread_id})
    service = SimulateUnderwritingsService(
        FakeSimulationRepository(
            [_row(id=1), _row(id=2)], {1: _item(id=1), 2: _item(id=2)}
        ),
        thread_repository=threads,
        discussion_service=discussions.service,
    )
    result = await service.get_all_simulated(page=1, page_size=25, interest_rate=0.06)
    by_id = {row.id: row.model_dump(mode="json") for row in result.data}
    assert by_id[1]["discussion"]["comment_count"] == 2
    assert by_id[2]["discussion"] == EMPTY
    assert by_id[1]["simulated"] is True
    assert len(threads.calls) == 1
