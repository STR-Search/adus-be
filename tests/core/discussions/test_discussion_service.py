"""DiscussionService against an in-memory repository.

The fake mirrors the repository's SQL semantics (counter updates, keyset
order, soft delete) so the service's orchestration can be tested without a
database. The SQL itself is covered by test_discussion_repository_sql.py.
"""

from datetime import timedelta

import pytest
import pytest_asyncio

from app.core.discussions.body.errors import InvalidBodyError, InvalidMentionError
from app.core.discussions.enums import SubjectType
from app.core.discussions.exceptions import (
    CommentNotFoundError,
    NotCommentAuthorError,
    RepliesNotSupportedError,
)
from app.core.discussions.service import DiscussionService
from app.core.enums import PageSize
from tests.core.discussions.conftest import (
    GONE,
    JANE,
    SAM,
    T0,
    FakeDiscussionRepository,
    FakeUserLookup,
    doc,
    mention,
    para,
    text,
)

AUTHOR = SAM.id


@pytest.fixture
def repo():
    return FakeDiscussionRepository()


@pytest.fixture
def service(repo, user_lookup):
    return DiscussionService(repo, user_lookup)


@pytest_asyncio.fixture
async def thread_id(service):
    return await service.create_thread(SubjectType.UNDERWRITING, AUTHOR)


def body(*inline):
    return doc(para(*inline))


async def post(service, thread_id, *inline, author=AUTHOR):
    return await service.create_comment(
        thread_id,
        author_user_id=author,
        body_version=1,
        body=body(*(inline or (text("hello"),))),
    )


# ── Threads & summaries ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_thread_and_empty_summary(service, repo, thread_id):
    assert repo.threads[thread_id].subject_type == "underwriting"
    summaries = await service.get_summaries([thread_id, 12345])
    assert set(summaries) == {thread_id}
    assert summaries[thread_id].comment_count == 0
    assert summaries[thread_id].last_comment_at is None


@pytest.mark.asyncio
async def test_create_thread_rejects_unknown_subject(service):
    with pytest.raises(ValueError):
        await service.create_thread("listing", AUTHOR)


@pytest.mark.asyncio
async def test_discard_thread(service, repo, thread_id):
    await service.discard_thread(thread_id)
    assert thread_id not in repo.threads


# ── Create ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_comment(service, repo, thread_id, user_lookup):
    detail = await post(service, thread_id, text("hi "), mention("42", label="x"))

    assert detail.thread_id == thread_id
    assert detail.author_user_id == AUTHOR
    assert detail.body == body(text("hi "), mention(42))
    assert not detail.is_deleted
    assert set(detail.users) == {SAM.id, JANE.id}
    assert detail.users[JANE.id].first_name == "Jane"

    stored = repo.comments[detail.id]
    assert stored.body_text == "hi @Jane Doe"
    assert repo.mentions == {(detail.id, JANE.id)}

    thread = repo.threads[thread_id]
    assert thread.comment_count == 1
    assert thread.last_comment_id == detail.id
    assert thread.last_comment_at == detail.created_at
    # mentions lookup + author lookup
    assert user_lookup.calls == [{JANE.id}, {SAM.id}]


@pytest.mark.asyncio
async def test_create_self_mention_needs_one_lookup(service, thread_id, user_lookup):
    await post(service, thread_id, mention(AUTHOR))
    assert user_lookup.calls == [{AUTHOR}]


@pytest.mark.asyncio
async def test_create_rejects_reply(service, repo, thread_id):
    with pytest.raises(RepliesNotSupportedError):
        await service.create_comment(
            thread_id,
            author_user_id=AUTHOR,
            body_version=1,
            body=body(text("x")),
            parent_comment_id=1,
        )
    assert repo.comments == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw", "error"),
    [
        (doc(para()), InvalidBodyError),
        (doc({"type": "heading"}), InvalidBodyError),
        (body(mention(99)), InvalidMentionError),
    ],
)
async def test_create_invalid_body_writes_nothing(service, repo, thread_id, raw, error):
    with pytest.raises(error):
        await service.create_comment(
            thread_id, author_user_id=AUTHOR, body_version=1, body=raw
        )
    assert repo.comments == {}
    assert repo.threads[thread_id].comment_count == 0


@pytest.mark.asyncio
async def test_last_comment_moves_forward_only(service, repo, thread_id):
    first = await post(service, thread_id)
    repo.tick()
    second = await post(service, thread_id)
    assert repo.threads[thread_id].last_comment_id == second.id

    # A comment whose transaction started earlier commits later.
    repo.clock = T0 - timedelta(seconds=5)
    late = await post(service, thread_id)
    thread = repo.threads[thread_id]
    assert thread.comment_count == 3
    assert thread.last_comment_id == second.id
    assert late.id > first.id


# ── Edit ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_edit_replaces_body_and_mentions(service, repo, thread_id):
    created = await post(service, thread_id, mention(42))
    repo.tick()
    edited = await service.edit_comment(
        created.id,
        user_id=AUTHOR,
        body_version=1,
        body=body(text("now "), mention(7)),
    )

    assert edited.body == body(text("now "), mention(7))
    assert edited.edited_at == repo.clock
    assert set(edited.users) == {SAM.id}
    assert repo.mentions == {(created.id, SAM.id)}
    assert repo.comments[created.id].body_text == "now @Sam Lee"
    assert repo.threads[thread_id].comment_count == 1


@pytest.mark.asyncio
async def test_edit_by_non_author_forbidden(service, thread_id):
    created = await post(service, thread_id)
    with pytest.raises(NotCommentAuthorError):
        await service.edit_comment(
            created.id, user_id=JANE.id, body_version=1, body=body(text("x"))
        )


@pytest.mark.asyncio
async def test_edit_missing_or_deleted_not_found(service, thread_id):
    with pytest.raises(CommentNotFoundError):
        await service.edit_comment(
            12345, user_id=AUTHOR, body_version=1, body=body(text("x"))
        )
    created = await post(service, thread_id)
    await service.delete_comment(created.id, user_id=AUTHOR)
    with pytest.raises(CommentNotFoundError):
        await service.edit_comment(
            created.id, user_id=AUTHOR, body_version=1, body=body(text("x"))
        )


@pytest.mark.asyncio
async def test_edit_invalid_body_keeps_old(service, repo, thread_id):
    created = await post(service, thread_id, text("keep"), mention(42))
    with pytest.raises(InvalidBodyError):
        await service.edit_comment(
            created.id, user_id=AUTHOR, body_version=1, body=doc(para())
        )
    assert repo.comments[created.id].body_text == "keep@Jane Doe"
    assert repo.mentions == {(created.id, JANE.id)}


# ── Delete ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_last_comment_recomputes(service, repo, thread_id):
    first = await post(service, thread_id)
    repo.tick()
    second = await post(service, thread_id, mention(42))

    await service.delete_comment(second.id, user_id=AUTHOR)
    thread = repo.threads[thread_id]
    assert thread.comment_count == 1
    assert thread.last_comment_id == first.id
    assert thread.last_comment_at == first.created_at
    assert repo.comments[second.id].deleted_at is not None
    # Mention rows are kept for deleted comments.
    assert (second.id, JANE.id) in repo.mentions

    await service.delete_comment(first.id, user_id=AUTHOR)
    assert thread.comment_count == 0
    assert thread.last_comment_id is None
    assert thread.last_comment_at is None


@pytest.mark.asyncio
async def test_delete_older_comment_keeps_last(service, repo, thread_id):
    first = await post(service, thread_id)
    repo.tick()
    second = await post(service, thread_id)
    await service.delete_comment(first.id, user_id=AUTHOR)
    thread = repo.threads[thread_id]
    assert thread.comment_count == 1
    assert thread.last_comment_id == second.id


@pytest.mark.asyncio
async def test_delete_checks(service, repo, thread_id):
    created = await post(service, thread_id)
    with pytest.raises(NotCommentAuthorError):
        await service.delete_comment(created.id, user_id=JANE.id)
    await service.delete_comment(created.id, user_id=AUTHOR)
    with pytest.raises(CommentNotFoundError):
        await service.delete_comment(created.id, user_id=AUTHOR)
    assert repo.threads[thread_id].comment_count == 0
    with pytest.raises(CommentNotFoundError):
        await service.delete_comment(12345, user_id=AUTHOR)


# ── List ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_without_thread_is_empty(service, user_lookup):
    page = await service.list_comments(None)
    assert page.items == [] and page.users == {}
    assert (page.total, page.page, page.page_size, page.pages) == (0, 1, 25, 0)
    assert user_lookup.calls == []


@pytest.mark.asyncio
async def test_list_paginates_newest_first(service, repo, thread_id):
    # Pairs share a timestamp so the id tiebreak matters.
    ids = []
    for i in range(55):
        ids.append((await post(service, thread_id)).id)
        if i % 2:
            repo.tick()

    pages = [
        await service.list_comments(thread_id, page=n, page_size=PageSize.SMALL)
        for n in (1, 2, 3)
    ]
    assert [len(p.items) for p in pages] == [25, 25, 5]
    assert all((p.total, p.pages, p.page_size) == (55, 3, 25) for p in pages)
    assert [p.page for p in pages] == [1, 2, 3]
    assert [c.id for p in pages for c in p.items] == list(reversed(ids))


@pytest.mark.asyncio
async def test_list_page_past_end_is_empty(service, thread_id):
    await post(service, thread_id)
    page = await service.list_comments(thread_id, page=2)
    assert page.items == [] and page.users == {}
    assert (page.total, page.pages) == (1, 1)


@pytest.mark.asyncio
async def test_list_exact_page(service, thread_id):
    for _ in range(25):
        await post(service, thread_id)
    page = await service.list_comments(thread_id)
    assert len(page.items) == 25
    assert page.pages == 1


@pytest.mark.asyncio
async def test_list_placeholders_and_users(repo, thread_id):
    lookup = FakeUserLookup([SAM, JANE])
    service = DiscussionService(repo, lookup)
    kept = await post(service, thread_id, mention(7))
    repo.tick()
    gone = await post(service, thread_id, mention(42), author=JANE.id)
    await service.delete_comment(gone.id, user_id=JANE.id)

    lookup.calls.clear()
    page = await service.list_comments(thread_id)
    by_id = {c.id: c for c in page.items}
    assert by_id[gone.id].is_deleted and by_id[gone.id].body is None
    assert by_id[kept.id].body == body(mention(7))
    # Placeholders count toward total (unlike threads.comment_count).
    assert page.total == 2
    assert repo.threads[thread_id].comment_count == 1
    # Jane is the deleted comment's author; her mention there is not used.
    assert set(page.users) == {SAM.id, JANE.id}
    assert lookup.calls == [{SAM.id, JANE.id}]


@pytest.mark.asyncio
async def test_list_users_include_deleted_users(repo, thread_id, user_lookup):
    service = DiscussionService(repo, user_lookup)
    await post(service, thread_id)
    # Author soft-deleted after posting: still in the map, flagged.
    repo.comments[next(iter(repo.comments))].author_user_id = GONE.id
    page = await service.list_comments(thread_id)
    assert page.users[GONE.id].is_deleted is True


@pytest.mark.asyncio
@pytest.mark.parametrize(("page", "page_size"), [(0, 25), (-1, 25), (1, 20), (1, 1000)])
async def test_list_rejects_bad_paging(service, thread_id, page, page_size):
    with pytest.raises(ValueError):
        await service.list_comments(thread_id, page=page, page_size=page_size)
