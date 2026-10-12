import pytest

from app.core.discussions.body.errors import InvalidBodyError, InvalidMentionError
from app.core.discussions.body.pipeline import process_body
from tests.core.discussions.conftest import doc, mention, para, text


@pytest.mark.asyncio
async def test_process_body_normalizes_and_resolves(user_lookup):
    raw = doc(
        para(
            text("hi "),
            mention("42", label="Jane"),
            text(" and "),
            mention(7),
            mention(42),
        )
    )
    result = await process_body(1, raw, user_lookup)

    assert result.body == doc(
        para(text("hi "), mention(42), text(" and "), mention(7), mention(42))
    )
    assert result.body_text == "hi @Jane Doe and @Sam Lee@Jane Doe"
    assert result.mention_user_ids == (42, 7)
    assert user_lookup.calls == [{42, 7}]  # one lookup, distinct ids


@pytest.mark.asyncio
async def test_no_mentions_skips_lookup(user_lookup):
    result = await process_body(1, doc(para(text("plain"))), user_lookup)
    assert result.mention_user_ids == ()
    assert user_lookup.calls == []


@pytest.mark.asyncio
async def test_unknown_and_deleted_mentions_rejected(user_lookup):
    raw = doc(para(mention(42), mention(99), mention(12345)))
    with pytest.raises(InvalidMentionError) as exc:
        await process_body(1, raw, user_lookup)
    assert exc.value.user_ids == [99, 12345]


@pytest.mark.asyncio
async def test_empty_body_rejected_before_lookup(user_lookup):
    with pytest.raises(InvalidBodyError):
        await process_body(1, doc(para()), user_lookup)
    assert user_lookup.calls == []


@pytest.mark.asyncio
async def test_limits_run_before_parsing(user_lookup, monkeypatch):
    def fail_parse(*_):
        raise AssertionError("parser must not run on an oversized body")

    monkeypatch.setattr("app.core.discussions.body.pipeline.parse_body", fail_parse)
    with pytest.raises(InvalidBodyError, match="characters"):
        await process_body(1, doc(para(text("a" * 10_001))), user_lookup)


@pytest.mark.asyncio
async def test_invalid_shape_rejected(user_lookup):
    with pytest.raises(InvalidBodyError):
        await process_body(
            1, doc({"type": "heading", "content": [text("x")]}), user_lookup
        )
